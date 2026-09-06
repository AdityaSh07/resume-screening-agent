
from __future__ import annotations

import asyncio
import hashlib
import logging

from langgraph.graph import StateGraph

from app.config import LLM_BATCH_SIZE, LLM_BATCH_WAIT_SECONDS
from app.config import TEST_LINK
from app.document_loader import load_candidates
from app.analyze_jd import analyze_jd
from app.get_jd import process_job_description
from app.services.email_service import email_service
from app.graph.candidate_subgraph.graph import candidate_graph
from app.candidate_identity import extract_candidate_identity
from app.database import save_shortlisted_candidates
from .state import ScreeningState
from langchain_core.documents import Document


logger = logging.getLogger(__name__)


builder = StateGraph(ScreeningState)


# ---------------------------------------------------------
# Node: load_candidates
# ---------------------------------------------------------

def load_candidates_node(state: ScreeningState):
    candidates = load_candidates(
        state["candidates_file_path"]
    )
    return {"candidates": candidates}


builder.add_node(
    "load_candidates",
    load_candidates_node,
)


# ---------------------------------------------------------
# Node: process_job_description
# ---------------------------------------------------------

async def process_job_description_node(
    state: ScreeningState,
):
    jd_text = await process_job_description(
        state.get("jd_file"),
        state.get("jd_text"),
    )
    return {"jd_text": jd_text}


builder.add_node(
    "process_job_description",
    process_job_description_node,
)


# ---------------------------------------------------------
# Node: analyze_jd  (LLM — once per job, rate-limited inside)
# ---------------------------------------------------------

builder.add_node(
    "analyze_jd",
    analyze_jd,
)


# ---------------------------------------------------------
# Node: evaluate_candidates
# ---------------------------------------------------------

def _batched(items: list, size: int):
    """Yield successive `size`-sized chunks from `items`."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def evaluate_candidates_node(
    state: ScreeningState,
) -> dict:
    """
    Rate-limit-safe sequential candidate evaluation.

    Processes candidates in batches of `LLM_BATCH_SIZE`.
    After each batch (except the last) waits `LLM_BATCH_WAIT_SECONDS`
    to allow the LLM TPM window to reset.

    Candidates within a batch are processed concurrently using
    asyncio.gather — but because each LLM call acquires a token slot
    from `llm_rate_limiter` first, the total in-flight token load
    stays within budget.

    With the default BATCH_SIZE=1 this is fully sequential and is the
    safest option for an 8 K TPM limit.
    """
    candidates: list[Document] = state.get("candidates") or []
    jd_requirements = state.get("jd_requirements")

    if not candidates:
        logger.warning(
            "evaluate_candidates_node: no candidates to process"
        )
        return {"candidate_results": []}

    all_results: list[dict] = []
    batches = list(_batched(candidates, LLM_BATCH_SIZE))
    total_batches = len(batches)

    logger.info(
        "Starting candidate evaluation: %d candidates, "
        "%d batch(es) of up to %d, "
        "%ds wait between batches.",
        len(candidates),
        total_batches,
        LLM_BATCH_SIZE,
        LLM_BATCH_WAIT_SECONDS,
    )

    for batch_idx, batch in enumerate(batches, start=1):

        logger.info(
            "Processing batch %d/%d (%d candidate(s)) …",
            batch_idx,
            total_batches,
            len(batch),
        )

        # Run all candidates in this batch concurrently.
        # The rate limiter inside each subgraph node serialises
        # actual LLM calls if needed.
        async def run_one(candidate: Document) -> dict:
            try:
                result = await candidate_graph.ainvoke(
                    {
                        "job_id": state.get("job_id"),
                        "candidate": candidate,
                        "jd_requirements": jd_requirements,
                    }
                )
                return result or {}
            except Exception as exc:
                logger.error(
                    "Candidate evaluation failed: %s",
                    str(exc)[:200],
                )
                return {"error": str(exc)[:200]}

        batch_results = await asyncio.gather(
            *[run_one(c) for c in batch],
            return_exceptions=False,
        )

        all_results.extend(batch_results)

        # Wait between batches (not after the last one)
        if batch_idx < total_batches:
            logger.info(
                "Batch %d/%d done. Waiting %ds before next batch …",
                batch_idx,
                total_batches,
                LLM_BATCH_WAIT_SECONDS,
            )
            await asyncio.sleep(LLM_BATCH_WAIT_SECONDS)

    logger.info(
        "Candidate evaluation complete. %d results collected.",
        len(all_results),
    )

    return {"candidate_results": all_results}


builder.add_node(
    "evaluate_candidates",
    evaluate_candidates_node,
)


# ---------------------------------------------------------
# Node: rank_candidates
# ---------------------------------------------------------

def rank_candidates_node(state: ScreeningState) -> dict:
    """
    Sort evaluated candidates by overall_score descending.
    Populates shortlisted_candidates with candidates that
    have shortlisted=True.
    """
    results: list[dict] = state.get("candidate_results") or []

    # Sort by overall_score descending (None scores treated as 0)
    sorted_results = sorted(
        results,
        key=lambda r: r.get("overall_score") or 0.0,
        reverse=True,
    )

    # A candidate subgraph result can be emitted more than once by a retry or
    # graph state merge. Keep the highest-ranked copy only.
    ranked: list[dict] = []
    seen_candidates: set[str] = set()
    for result in sorted_results:
        candidate = result.get("candidate") or {}
        if isinstance(candidate, dict):
            candidate_key = candidate.get("page_content", "")
        else:
            candidate_key = candidate.page_content
        if candidate_key in seen_candidates:
            continue
        seen_candidates.add(candidate_key)
        ranked.append(result)

    shortlisted = [
        r for r in ranked if r.get("shortlisted") is True
    ]

    logger.info(
        "Ranked %d candidates. %d shortlisted.",
        len(ranked),
        len(shortlisted),
    )

    return {
        "candidate_results": ranked,
        "shortlisted_candidates": shortlisted,
    }


builder.add_node(
    "rank_candidates",
    rank_candidates_node,
)


async def persist_shortlisted_candidates_node(state: ScreeningState) -> dict:
    shortlisted = state.get("shortlisted_candidates") or []
    if not shortlisted:
        return {"database_results": []}

    candidates_to_store: list[dict] = []
    for result in shortlisted:
        candidate = result.get("candidate")
        if isinstance(candidate, dict):
            candidate = Document(
                page_content=candidate.get("page_content", ""),
                metadata=candidate.get("metadata", {}),
            )
        if not isinstance(candidate, Document):
            logger.warning("Skipping shortlisted result without a candidate Document")
            continue
        enriched = dict(result)
        identity = await extract_candidate_identity(candidate)
        if not identity.candidate_id:
            identity.candidate_id = hashlib.sha256(
                candidate.page_content.encode("utf-8")
            ).hexdigest()[:24]
        enriched["identity"] = identity
        candidates_to_store.append(enriched)

    database_results = await save_shortlisted_candidates(
        job_id=state["job_id"],
        candidates=candidates_to_store,
    )
    return {"database_results": database_results}


builder.add_node(
    "persist_shortlisted_candidates",
    persist_shortlisted_candidates_node,
)


def _candidate_field(candidate: Document | dict, field_name: str) -> str:
    if isinstance(candidate, dict):
        content = candidate.get("page_content", "")
    else:
        content = candidate.page_content

    prefix = f"{field_name}:"
    for line in content.splitlines():
        if line.lower().startswith(prefix):
            return line[len(prefix):].strip()
    return ""


async def send_shortlisted_test_emails_node(
    state: ScreeningState,
) -> dict:
    shortlisted = state.get("shortlisted_candidates") or []

    if not shortlisted:
        logger.info("No shortlisted candidates; no test emails to send.")
        return {"email_results": []}

    if not TEST_LINK:
        logger.warning(
            "TEST_LINK is not configured; skipping shortlisted test emails."
        )
        return {
            "email_results": [
                {
                    "status": "skipped",
                    "reason": "TEST_LINK is not configured",
                }
            ]
        }

    email_results: list[dict] = []
    for result in shortlisted:
        candidate = result.get("candidate") or {}
        email = _candidate_field(candidate, "email")
        name = _candidate_field(candidate, "name") or "Candidate"

        if not email:
            email_results.append(
                {"status": "skipped", "name": name, "reason": "email missing"}
            )
            continue

        sent = await email_service.send_test_invitation(
            to_email=email,
            candidate_name=name,
            test_link=TEST_LINK,
        )
        email_results.append(
            {
                "status": "sent" if sent else "failed",
                "name": name,
                "email": email,
            }
        )

    return {"email_results": email_results}


builder.add_node(
    "send_shortlisted_test_emails",
    send_shortlisted_test_emails_node,
)
