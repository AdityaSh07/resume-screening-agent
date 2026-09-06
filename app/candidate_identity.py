from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.llm import llm_for_candidate_identity
from app.rate_limiter import llm_rate_limiter
from app.schemas import CandidateIdentity


candidate_identity_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
Extract the candidate's name, email address, and candidate/application identifier
from the candidate record below.

The record may use any CSV column names. Prefer candidate_id or application_id
for the identifier. Read values from the content rather than assuming fixed
column names. Return an empty string only when a value is not present. Do not
invent or normalize values beyond trimming whitespace.
Return the provided structured schema only.
""",
    ),
    ("human", "Candidate record:\n\n{candidate_text}"),
])


async def extract_candidate_identity(candidate: Document) -> CandidateIdentity:
    messages = candidate_identity_prompt.format_messages(
        candidate_text=candidate.page_content,
    )
    return await llm_rate_limiter.ainvoke_with_retry(
        llm_for_candidate_identity,
        messages,
    )