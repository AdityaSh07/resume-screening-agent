from langchain_core.prompts import ChatPromptTemplate

from app.graph.state import ScreeningState
from app.llm import llm_for_jd
from app.rate_limiter import llm_rate_limiter
from app.database import save_job


jd_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are an expert technical recruiter and AI hiring evaluator.

Analyze the provided Job Description and extract the requirements
that should be used to evaluate candidates.

Rules:
- Extract only requirements supported by the job description.
- Do not invent or assume requirements.
- Distinguish required skills from preferred skills.
- Identify programming languages explicitly mentioned.
- Extract required and preferred experience separately.
- Extract education requirements.
- Extract key responsibilities.
- Extract project requirements.
- Extract signals that can later be evaluated from a candidate's
  GitHub profile and repositories.
- Extract important technical keywords for candidate matching.
- Keep each list concise and include only the most important items.
- Do not repeat equivalent requirements.

The output must follow the provided structured schema.
"""
    ),
    (
        "human",
        """
Analyze this Job Description:

{jd_text}
"""
    ),
])

async def analyze_jd(state: ScreeningState):
    messages = jd_prompt.format_messages(
        jd_text=state["jd_text"]
    )

    response = await llm_rate_limiter.ainvoke_with_retry(
        llm_for_jd,
        messages,
    )

    jd_requirements = response.model_dump() if hasattr(response, "model_dump") else response
    await save_job(
        job_id=state["job_id"],
        jd_text=state["jd_text"],
        jd_requirements=jd_requirements,
    )
    return {"jd_requirements": response}
