from langchain_groq import ChatGroq
from .schemas import JDRequirements, ResumeEvaluation

from dotenv import load_dotenv

load_dotenv()


llm = ChatGroq(
    model="qwen/qwen3.8-27b",
    temperature=0,
    max_tokens=800,
)


llm_for_jd = llm.with_structured_output(JDRequirements)

llm_for_resume = llm.with_structured_output(ResumeEvaluation)

