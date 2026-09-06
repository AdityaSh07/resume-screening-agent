from __future__ import annotations

import logging

from app.config import TEST_PASSING_SCORE
from app.database import get_shortlisted_candidates, update_test_results
from app.document_loader import load_candidates
from app.llm import llm_for_test_result
from app.rate_limiter import llm_rate_limiter
from app.graph.test_results.state import TestResultsState
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


extract_test_result_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
Extract one candidate's test result from the record below.

CSV column names may vary. Identify candidate_id or application_id first, then
email, and use candidate name only as a fallback. Map the logical
aptitude and coding scores by meaning, not by exact column name. For example,
"test_la" can mean logical aptitude and "test_code" can mean coding. Preserve
the source score scale. Return null when a score is absent. Return only the
provided structured schema.
""",
    ),
    ("human", "Test result record:\n\n{test_record}"),
])


def load_test_results_node(state: TestResultsState) -> dict:
    documents = load_candidates(state["test_results_file_path"])
    if not documents:
        raise ValueError("The test-results file contains no rows.")
    return {"test_documents": documents}


async def extract_test_results_node(state: TestResultsState) -> dict:
    extracted: list[dict] = []
    for document in state.get("test_documents", []):
        try:
            messages = extract_test_result_prompt.format_messages(
                test_record=document.page_content,
            )
            result = await llm_rate_limiter.ainvoke_with_retry(
                llm_for_test_result,
                messages,
            )
        except Exception as exc:
            logger.warning("Test-result row could not be extracted: %s", str(exc)[:200])
            extracted.append({"status": "invalid", "reason": "row extraction failed"})
            continue

        email = result.email.strip().lower()
        candidate_id = result.candidate_id.strip()
        name = result.name.strip()
        if not email and not candidate_id and not name:
            extracted.append({"status": "skipped", "reason": "candidate identifier missing"})
            continue

        logical = result.logical_aptitude_score
        coding = result.coding_test_score
        available_scores = [score for score in (logical, coding) if score is not None]
        test_score = (
            sum(available_scores) / len(available_scores)
            if available_scores
            else None
        )
        extracted.append(
            {
                "name": name,
                "candidate_id": candidate_id,
                "email": email,
                "logical_aptitude_score": logical,
                "coding_test_score": coding,
                "test_score": test_score,
                "interview_eligible": (
                    test_score is not None and test_score >= TEST_PASSING_SCORE
                ),
            }
        )
    return {"extracted_results": extracted}


async def persist_test_results_node(state: TestResultsState) -> dict:
    persisted: list[dict] = []
    candidates = await get_shortlisted_candidates(state["job_id"])
    seen_keys: set[str] = set()
    for result in state.get("extracted_results", []):
        email = result.get("email")
        candidate_id = result.get("candidate_id", "")
        name = result.get("name", "")
        match_key = candidate_id or email or name.lower()
        if not match_key or match_key in seen_keys:
            continue
        seen_keys.add(match_key)

        if candidate_id:
            matches = [
                candidate for candidate in candidates
                if candidate.get("candidate_id") == candidate_id
            ]
        elif email:
            matches = [
                candidate for candidate in candidates
                if candidate.get("email", "").lower() == email
            ]
            if len(matches) > 1 and name:
                named_matches = [
                    candidate for candidate in matches
                    if candidate.get("name", "").strip().lower() == name.lower()
                ]
                if named_matches:
                    matches = named_matches
        else:
            matches = [
                candidate for candidate in candidates
                if candidate.get("name", "").lower() == name.lower()
            ]
        if len(matches) != 1:
            persisted.append({**result, "status": "ambiguous" if len(matches) > 1 else "not_found"})
            continue

        candidate = matches[0]
        test_score = result.get("test_score")
        overall_score = candidate.get("overall_score") or 0
        final_score = (
            overall_score * 0.6 + test_score * 0.4
            if test_score is not None else None
        )
        qualification_status = (
            "interview_eligible"
            if result.get("interview_eligible") and final_score is not None
            else "rejected"
        )
        result["final_score"] = final_score
        result["qualification_status"] = qualification_status
        result["id"] = candidate["id"]

        updated = await update_test_results(
            job_id=state["job_id"],
            email=email,
            test_results=result,
            candidate_id=candidate_id or candidate.get("candidate_id", ""),
            candidate_name=name,
            final_score=final_score,
            qualification_status=qualification_status,
        )
        persisted.append(
            {
                **result,
                "status": "updated" if updated else "not_found",
            }
        )
    return {
        "persisted_results": persisted,
        "initial_shortlist_count": len(candidates),
        "matched_count": sum(item.get("status") == "updated" for item in persisted),
        "final_shortlist_count": sum(
            item.get("qualification_status") == "interview_eligible"
            for item in persisted
        ),
    }
