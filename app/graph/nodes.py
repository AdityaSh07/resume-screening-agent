"""
Main graph nodes for the candidate screening pipeline.

The key node here is `evaluate_candidates_node`, which replaces the
old `Send` fan-out with a rate-limit-safe sequential (or small-batch)
evaluation loop.

Rate-limiting strategy
----------------------
Candidates are processed in batches of `LLM_BATCH_SIZE` (default: 1).
After each complete batch (except the last) the node waits
`LLM_BATCH_WAIT_SECONDS` (default: 60 s) so the LLM API's TPM window
resets before the next batch starts.

Within a single candidate's subgraph run the resume-eval and
github-eval branches may execute concurrently (as designed), but each
individually acquires a token slot from the shared `llm_rate_limiter`
before firing, so the combined usage is still bounded.
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.graph import StateGraph

from app.config import LLM_BATCH_SIZE, LLM_BATCH_WAIT_SECONDS
from app.document_loader import load_candidates
from app.analyze_jd import analyze_jd
from app.get_jd import process_job_description
from app.graph.candidate_subgraph.graph import candidate_graph
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
    ranked = sorted(
        results,
        key=lambda r: r.get("overall_score") or 0.0,
        reverse=True,
    )

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
