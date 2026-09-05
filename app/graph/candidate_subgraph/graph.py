from langgraph.graph import StateGraph, START, END

from .state import CandidateState
from .nodes import (
    extract_candidate_links_node,
    download_resume_node,
    resume_eval_node,
    analyze_github_node,
)


candidate_builder = StateGraph(CandidateState)

candidate_builder.add_node(
    "extract_candidate_links",
    extract_candidate_links_node,
)

candidate_builder.add_node(
    "download_resume",
    download_resume_node,
)

candidate_builder.add_node(
    "resume_eval",
    resume_eval_node,
)

candidate_builder.add_node(
    "analyze_github",
    analyze_github_node,
)


candidate_builder.add_edge(
    START,
    "extract_candidate_links",
)

candidate_builder.add_edge(
    "extract_candidate_links",
    "download_resume",
)

candidate_builder.add_edge(
    "download_resume",
    "resume_eval",
)

candidate_builder.add_edge(
    "extract_candidate_links",
    "analyze_github",
)

candidate_builder.add_edge(
    "resume_eval",
    END,
)

candidate_builder.add_edge(
    "analyze_github",
    END,
)


candidate_graph = candidate_builder.compile()
