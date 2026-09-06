"""
Central configuration for the candidate screening platform.

All settings are read from environment variables (via .env loaded by dotenv).
Never hardcode secrets here — use .env.example as the template.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------
# LLM / Rate Limiting
# ---------------------------------------------------------

# Hard limit imposed by the Groq free tier (~8 000 tokens per minute).
LLM_TPM_LIMIT: int = int(os.getenv("LLM_TPM_LIMIT", "8000"))

# Number of candidates processed in a single batch before waiting.
# Keep at 1 unless you have confirmed extra token budget.
LLM_BATCH_SIZE: int = int(os.getenv("LLM_BATCH_SIZE", "1"))

# Seconds to wait between evaluation batches so the TPM window resets.
LLM_BATCH_WAIT_SECONDS: int = int(
    os.getenv("LLM_BATCH_WAIT_SECONDS", "60")
)

# Maximum LLM retry attempts on 429 / transient errors.
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Base backoff (seconds) for exponential retry: wait = BASE * 2^attempt
LLM_RETRY_BASE_WAIT: float = float(
    os.getenv("LLM_RETRY_BASE_WAIT", "5")
)


# ---------------------------------------------------------
# LLM Model
# ---------------------------------------------------------

LLM_MODEL: str = os.getenv(
    "LLM_MODEL", "qwen/qwen3.8-27b"
)

LLM_TEMPERATURE: float = float(
    os.getenv("LLM_TEMPERATURE", "0")
)

LLM_MAX_TOKENS: int = int(
    os.getenv("LLM_MAX_TOKENS", "800")
)


# ---------------------------------------------------------
# Email (Resend)
# ---------------------------------------------------------

RESEND_API_KEY: str | None = os.getenv("RESEND_API_KEY")

EMAIL_FROM: str = os.getenv(
    "EMAIL_FROM", "amssre.15001@gmail.com"
)


# ---------------------------------------------------------
# GitHub
# ---------------------------------------------------------

GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")


# ---------------------------------------------------------
# Database
# ---------------------------------------------------------

POSTGRE_DB_URL: str | None = os.getenv("POSTGRE_DB_URL")

