from .state import ScreeningState
from .nodes import builder
from langgraph.graph import START, END
from langgraph.types import Send



builder.add_edge(
    START,
    "load_candidates",
)

builder.add_edge(
    "load_candidates",
    "process_job_description",
)

builder.add_edge(
    "process_job_description",
    "analyze_jd",
)

def send_candidates(state: ScreeningState):

    return [
        Send(
            "extract_candidate_links",
            {
                "job_id": state["job_id"],
                "candidate": candidate,
                "jd_requirements": state["jd_requirements"],
            },
        )
        for candidate in state["candidates"]
    ]

builder.add_conditional_edges(
    "analyze_jd",
    send_candidates,
)

builder.add_edge(
    "extract_candidate_links",
    "download_resume",
)

builder.add_edge(
    "extract_candidate_links",
    "analyze_github",
)

builder.add_edge(
    "extract_candidate_links",
    "analyze_github",
)

builder.add_edge(
    "analyze_github",
    END,
)

graph = builder.compile()