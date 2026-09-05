from langgraph.graph import StateGraph, START, END
from app.get_jd import process_job_description
from app.analyze_jd import analyze_jd
from app.document_loader import load_candidates
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


