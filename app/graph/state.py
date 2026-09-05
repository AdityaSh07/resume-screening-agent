from typing import TypedDict
from langchain_core.documents import Document


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

    # Current candidate when Send() fans out
    candidate: Document

    # Extracted candidate links
    resume_url: str | None
    github_url: str | None

    # Processing results
    resume_data: str | None
    github_data: dict | None

    # Final candidate results
    results: list[dict]