from typing import TypedDict, Annotated
from langchain_core.documents import Document
import operator


class ScreeningState(TypedDict, total=False):
    # Job-level information
    job_id: str

    # Input files
    candidates_file_path: str

    jd_file_path: str | None
    jd_text: str | None

    # Loaded candidate documents
    candidates: list[Document]

    # JD analysis result
    jd_requirements: dict

    # Evaluated candidate results (accumulated by evaluate_candidates_node)
    # Each entry is the final CandidateState dict for one candidate.
    candidate_results: Annotated[list[dict], operator.add]

    # Shortlisted candidates after scoring (populated by shortlist_node)
    shortlisted_candidates: list[dict] | None

    # Delivery results for the post-ranking candidate notifications
    email_results: list[dict]