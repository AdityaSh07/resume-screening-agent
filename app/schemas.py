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