from langchain_core.documents import Document
from typing import TypedDict

class CandidateState(TypedDict, total=False):
    job_id: str
    candidate: Document
    jd_requirements: dict

    resume_url: str | None
    github_url: str | None

    resume_data: str | None
    resume_score: float | None
    resume_reasoning: str | None

    github_data: dict | None
    github_text: str | None
    github_score: float | None
    github_reasoning: str | None

    overall_score: float | None
    shortlisted: bool | None