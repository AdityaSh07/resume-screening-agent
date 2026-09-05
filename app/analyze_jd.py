from langchain_core.prompts import ChatPromptTemplate

from app.graph.state import ScreeningState
from app.llm import llm_for_jd


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

    response = await llm_for_jd.ainvoke(messages)

    return {
        "jd_requirements": response
    }
