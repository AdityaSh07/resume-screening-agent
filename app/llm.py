from langchain_groq import ChatGroq

from app.config import (
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
)
from app.schemas import GitHubEvaluation, JDRequirements, ResumeEvaluation

from dotenv import load_dotenv

load_dotenv()


llm = ChatGroq(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
    max_tokens=LLM_MAX_TOKENS,
)


llm_for_jd = llm.with_structured_output(JDRequirements)

llm_for_resume = llm.with_structured_output(ResumeEvaluation)

llm_for_github = llm.with_structured_output(GitHubEvaluation)