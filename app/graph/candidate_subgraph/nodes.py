from app.graph.candidate_subgraph.services.extract_resume_github import extract_candidate_links
from app.graph.candidate_subgraph.services.get_resume import download_resume
from app.llm import llm_for_resume, llm_for_github
from langchain.schema import Document
from .prompts.resume_eval_prompt import resume_eval_prompt
from .prompts.github_eval_prompt import github_eval_prompt
from .state import CandidateState

from .services.get_github_details import analyze_github

def extract_candidate_links_node(
    state: CandidateState,
):

    candidate = state["candidate"]

    # LangGraph may represent the Document as a dict
    if isinstance(candidate, dict):
        candidate = Document(
            page_content=candidate["page_content"],
            metadata=candidate.get(
                "metadata",
                {},
            ),
        )

    links = extract_candidate_links(candidate)

    return {
        "resume_url": links["resume_url"],
        "github_url": links["github_url"],
    }


from langchain_community.document_loaders import PyPDFLoader


def download_resume_node(state: CandidateState):

    resume_path = download_resume(
        state.get("resume_url")
    )

    loader = PyPDFLoader(resume_path)

    documents = loader.load()

    resume_text = "\n\n".join(
        document.page_content
        for document in documents
    )

    return {
        "resume_data": resume_text
    }

def resume_eval_node(state: CandidateState):

    messages = resume_eval_prompt.format_messages(
        jd_requirements=state["jd_requirements"],
        resume_data=state["resume_data"],
    )

    evaluation = llm_for_resume.invoke(messages)

    return {
        "resume_score": evaluation.score,
        "resume_reasoning": evaluation.reasoning,
    }


async def analyze_github_node(state: CandidateState):

    github_data = await analyze_github(
        state.get("github_url"),
        state.get("jd_requirements"),
    )

    return {
        "github_data": github_data
    }


async def github_eval_node(state: CandidateState):

    messages = github_eval_prompt.format_messages(
        jd_requirements=state["jd_requirements"],
        github_text=state.get("github_text"),
    )

    result = await llm_for_github.ainvoke(
        messages
    )

    return {
        "github_score": result.score,
        "github_reasoning": result.reasoning,
    }


def overall_score_node(state: CandidateState):

    resume_score = state.get("resume_score") or 0
    github_score = state.get("github_score") or 0

    overall_score = (
        resume_score * 0.7
        + github_score * 0.3
    )

    shortlisted = overall_score >= 70

    return {
        "overall_score": overall_score,
        "shortlisted": shortlisted,
    }
