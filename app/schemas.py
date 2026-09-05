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