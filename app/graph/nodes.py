from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from app.get_jd import process_job_description
from app.analyze_jd import analyze_jd
from app.document_loader import load_candidates
from app.extract_resume_github import extract_candidate_links
from app.get_resume import download_resume
from app.get_github_details import analyze_github
from .state import ScreeningState
from langchain_core.documents import Document


builder = StateGraph(ScreeningState)


# ---------------------------------------------------------
# Nodes
# ---------------------------------------------------------
def load_candidates_node(state: ScreeningState):
    candidates = load_candidates(
        state["candidates_file_path"]
    )

    return {
        "candidates": candidates
    }
builder.add_node(
    "load_candidates",
    load_candidates_node,
)


async def process_job_description_node(state: ScreeningState):
    jd_text = await process_job_description(
        state.get("jd_file"),
        state.get("jd_text"),
    )

    return {
        "jd_text": jd_text
    }

builder.add_node(
    "process_job_description",
    process_job_description_node,
)

builder.add_node(
    "analyze_jd",
    analyze_jd,
)

def extract_candidate_links_node(
    state: ScreeningState,
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
builder.add_node(
    "extract_candidate_links",
    extract_candidate_links_node,
)

def download_resume_node(state: ScreeningState):
    resume_path = download_resume(
        state.get("resume_url")
    )

    return {
        "resume_data": resume_path
    }
builder.add_node(
    "download_resume",
    download_resume_node,
)


async def analyze_github_node(state: ScreeningState):

    github_data = await analyze_github(
        state.get("github_url")
    )

    return {
        "github_data": github_data
    }
builder.add_node(
    "analyze_github",
    analyze_github_node,
)