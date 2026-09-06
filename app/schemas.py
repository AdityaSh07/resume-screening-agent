from pydantic import BaseModel, Field


class JDRequirements(BaseModel):
    job_title: str

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)

    required_languages: list[str] = Field(default_factory=list)

    required_experience_years: float | None = None
    preferred_experience_years: float | None = None

    education_requirements: list[str] = Field(default_factory=list)

    responsibilities: list[str] = Field(default_factory=list)

    project_requirements: list[str] = Field(default_factory=list)

    github_signals: list[str] = Field(default_factory=list)

    keywords: list[str] = Field(default_factory=list)


class ResumeEvaluation(BaseModel):
    score: float = Field(
        description="Overall resume match score from 0 to 100."
    )
    reasoning: str = Field(
        description="Brief explanation of why this score was given."
    )


class GitHubEvaluation(BaseModel):
    score: float = Field(
        description="Overall GitHub profile relevance score from 0 to 100."
    )

    reasoning: str = Field(
        description="Brief explanation of the candidate's GitHub relevance to the job."
    )


class CandidateIdentity(BaseModel):
    candidate_id: str = Field(default="", description="Candidate or application ID if present.")
    name: str = Field(description="Candidate's full name.")
    email: str = Field(description="Candidate's email address.")


class TestResultExtraction(BaseModel):
    name: str = Field(default="", description="Candidate's name if present.")
    candidate_id: str = Field(default="", description="Candidate or application ID if present.")
    email: str = Field(default="", description="Candidate's email address if present.")
    logical_aptitude_score: float | None = Field(
        default=None,
        description="Logical aptitude score, preserving the source scale.",
    )
    coding_test_score: float | None = Field(
        default=None,
        description="Coding test score, preserving the source scale.",
    )