from app.graph.candidate_subgraph.services.extract_resume_github import (
    extract_candidate_links,
)
from app.graph.candidate_subgraph.services.get_resume import download_resume
from app.llm import llm_for_github, llm_for_resume
from app.rate_limiter import llm_rate_limiter
from langchain.schema import Document
from langchain_community.document_loaders import PyPDFLoader
from pathlib import Path

from .prompts.github_eval_prompt import github_eval_prompt
from .prompts.resume_eval_prompt import resume_eval_prompt
from .services.get_github_details import analyze_github
from .state import CandidateState


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


def download_resume_node(state: CandidateState):

    resume_path = download_resume(
        state.get("resume_url")
    )

    if resume_path is None:
        return {"resume_data": None}

    try:
        loader = PyPDFLoader(resume_path)
        documents = loader.load()
        resume_text = "\n\n".join(
            document.page_content
            for document in documents
        )
    except Exception:
        resume_text = None
    finally:
        Path(resume_path).unlink(missing_ok=True)

    return {"resume_data": resume_text}


async def resume_eval_node(state: CandidateState):

    resume_data = state.get("resume_data") or ""

    if not resume_data.strip():
        # No resume available — return a zero score with explanation
        return {
            "resume_score": 0.0,
            "resume_reasoning": "Resume could not be downloaded or parsed.",
        }

    messages = resume_eval_prompt.format_messages(
        jd_requirements=state["jd_requirements"],
        resume_data=resume_data,
    )

    evaluation = await llm_rate_limiter.ainvoke_with_retry(
        llm_for_resume,
        messages,
    )

    return {
        "resume_score": evaluation.score,
        "resume_reasoning": evaluation.reasoning,
    }


async def analyze_github_node(state: CandidateState):

    github_result = await analyze_github(
        state.get("github_url"),
        state.get("jd_requirements"),
    )

    if github_result is None:
        return {
            "github_data": None,
            "github_text": None,
        }

    return {
        "github_data": github_result.get("github_data"),
        "github_text": github_result.get("github_text"),
    }


async def github_eval_node(state: CandidateState):

    github_text = state.get("github_text") or ""

    if not github_text.strip():
        return {
            "github_score": 0.0,
            "github_reasoning": (
                "No GitHub profile or relevant repositories found."
            ),
        }

    messages = github_eval_prompt.format_messages(
        jd_requirements=state["jd_requirements"],
        github_text=github_text,
    )

    result = await llm_rate_limiter.ainvoke_with_retry(
        llm_for_github,
        messages,
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

    shortlisted = overall_score >= 50

    return {
        "overall_score": overall_score,
        "shortlisted": shortlisted,
    }
