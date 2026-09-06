"""
Centralized LLM rate limiter for the candidate screening platform.

All LLM call sites must go through this module to avoid hitting
the Groq ~8 000 tokens-per-minute (TPM) limit.

Design
------
- Maintains a sliding-window token counter (1-minute window).
- Before each LLM call, `acquire(estimated_tokens)` checks whether
  adding the estimate would exceed the configured TPM budget.
- If it would, sleeps until enough of the window has drained.
- On 429 / rate-limit responses from the LLM API, retries with
  exponential backoff (up to LLM_MAX_RETRIES times).
- A module-level singleton `llm_rate_limiter` is provided so every
  import site shares the same token window.

Usage
-----
    from app.rate_limiter import llm_rate_limiter

    result = await llm_rate_limiter.ainvoke_with_retry(
        llm_chain,          # any LangChain Runnable
        messages,           # the input
        estimated_tokens=600,
    )
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from app.config import (
    LLM_BATCH_WAIT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_RETRY_BASE_WAIT,
    LLM_TPM_LIMIT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------

# Conservative tokens-per-character ratio for estimation when the LLM
# does not return usage metadata.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count: len(text) / 4, rounded up."""
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: Any) -> int:
    """
    Estimate token count for a list of LangChain messages.

    Falls back to a conservative default if structure is unexpected.
    """
    try:
        total = 0
        for msg in messages:
            if hasattr(msg, "content"):
                content = msg.content
            elif isinstance(msg, dict):
                content = msg.get("content", "")
            else:
                content = str(msg)

            if isinstance(content, str):
                total += estimate_tokens(content)
            elif isinstance(content, list):
                # Multi-modal content blocks
                for block in content:
                    if isinstance(block, dict):
                        total += estimate_tokens(
                            block.get("text", "")
                        )

        # Add a flat overhead for role tokens and formatting (~10 per message)
        total += len(messages) * 10

        return total

    except Exception:
        # Conservative fallback if we can't inspect messages
        return 500


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class LLMRateLimiter:
    """
    Sliding-window token rate limiter for LLM API calls.

    Parameters
    ----------
    tpm_limit:
        Maximum tokens allowed per 60-second window.
    window_seconds:
        Duration of the sliding window (default: 60).
    max_retries:
        Maximum retry attempts on 429 / transient errors.
    retry_base_wait:
        Base wait in seconds for exponential backoff.
    """

    def __init__(
        self,
        tpm_limit: int = LLM_TPM_LIMIT,
        window_seconds: float = 60.0,
        max_retries: int = LLM_MAX_RETRIES,
        retry_base_wait: float = LLM_RETRY_BASE_WAIT,
    ) -> None:
        self._tpm_limit = tpm_limit
        self._window = window_seconds
        self._max_retries = max_retries
        self._retry_base_wait = retry_base_wait

        # Each entry: (timestamp, tokens_used)
        self._usage: deque[tuple[float, int]] = deque()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_expired(self, now: float) -> None:
        """Remove entries older than the sliding window."""
        cutoff = now - self._window
        while self._usage and self._usage[0][0] < cutoff:
            self._usage.popleft()

    def _tokens_in_window(self, now: float) -> int:
        self._evict_expired(now)
        return sum(t for _, t in self._usage)

    def _oldest_entry_time(self) -> float | None:
        if self._usage:
            return self._usage[0][0]
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self, estimated_tokens: int) -> None:
        """
        Block until there is room in the TPM window for `estimated_tokens`.

        This must be called before each LLM invocation.
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                used = self._tokens_in_window(now)

                if used + estimated_tokens <= self._tpm_limit:
                    # Record usage and proceed
                    self._usage.append((now, estimated_tokens))
                    logger.debug(
                        "Rate limiter: acquired %d tokens "
                        "(%d/%d used in window)",
                        estimated_tokens,
                        used + estimated_tokens,
                        self._tpm_limit,
                    )
                    return

                # Need to wait until oldest entry leaves the window
                oldest = self._oldest_entry_time()

                if oldest is None:
                    # Window is somehow empty but still over limit —
                    # this shouldn't happen; wait a short time
                    wait_s = 1.0
                else:
                    # Wait until that entry is outside the window
                    wait_s = max(
                        0.1,
                        (oldest + self._window) - now + 0.1,
                    )

                logger.info(
                    "Rate limiter: TPM window full "
                    "(%d/%d tokens used). Waiting %.1fs …",
                    used,
                    self._tpm_limit,
                    wait_s,
                )

                # Release lock while sleeping so other coroutines
                # can check but they'll block on the same condition.
                self._lock.release()
                try:
                    await asyncio.sleep(wait_s)
                finally:
                    await self._lock.acquire()

    async def ainvoke_with_retry(
        self,
        runnable: Any,
        input_data: Any,
        *,
        estimated_tokens: int | None = None,
    ) -> Any:
        """
        Invoke a LangChain Runnable with rate-limit protection and retry.

        Parameters
        ----------
        runnable:
            A LangChain chain/LLM (anything with `.ainvoke()`).
        input_data:
            The input passed to `.ainvoke()`.
        estimated_tokens:
            Token estimate for this call. If None, estimated from messages.

        Returns
        -------
        The result from `runnable.ainvoke(input_data)`.

        Raises
        ------
        RuntimeError if all retries are exhausted.
        """
        if estimated_tokens is None:
            try:
                estimated_tokens = estimate_messages_tokens(input_data)
            except Exception:
                estimated_tokens = 500

        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):

            await self.acquire(estimated_tokens)

            try:
                result = await runnable.ainvoke(input_data)
                return result

            except Exception as exc:
                last_exc = exc
                exc_str = str(exc)
                exc_type = type(exc).__name__

                # Detect transient provider failures without importing
                # provider-specific exception types.
                is_retryable = (
                    "429" in exc_str
                    or "rate_limit" in exc_str.lower()
                    or "rate limit" in exc_str.lower()
                    or "too many requests" in exc_str.lower()
                    or "ratelimit" in exc_str.lower()
                    or "tool_use_failed" in exc_str.lower()
                    or "failed_generation" in exc_str.lower()
                )

                if is_retryable:
                    wait_s = min(
                        self._retry_base_wait * (2 ** attempt),
                        LLM_BATCH_WAIT_SECONDS,
                    )
                    logger.warning(
                        "Retryable LLM failure (%s). "
                        "Attempt %d/%d. Retrying in %.0fs …",
                        exc_type,
                        attempt + 1,
                        self._max_retries,
                        wait_s,
                    )
                    if attempt < self._max_retries:
                        await asyncio.sleep(wait_s)
                        continue

                # Non-rate-limit errors: log and re-raise immediately
                logger.error(
                    "LLM invocation failed (%s): %s",
                    exc_type,
                    # Truncate to avoid leaking large payloads
                    exc_str[:200],
                )
                raise

        raise RuntimeError(
            f"LLM call failed after {self._max_retries + 1} attempts. "
            f"Last error: {last_exc}"
        )


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere
# ---------------------------------------------------------------------------

llm_rate_limiter = LLMRateLimiter()

