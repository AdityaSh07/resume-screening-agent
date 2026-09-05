from .state import ScreeningState
from .nodes import builder
from .candidate_subgraph.graph import candidate_graph

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
            "candidate_processing",
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


builder.add_node(
    "candidate_processing",
    candidate_graph,
)


builder.add_edge(
    "candidate_processing",
    END,
)


graph = builder.compile()



