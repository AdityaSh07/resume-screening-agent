from langchain.schema import Document
from typing import TypedDict

class CandidateState(TypedDict, total=False):
    job_id: str
    candidate: Document
    jd_requirements: dict

    resume_url: str | None
    github_url: str | None

    resume_data: str | None
    resume_score: float | None

    github_data: dict | None