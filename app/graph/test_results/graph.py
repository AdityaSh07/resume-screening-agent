from langgraph.graph import END, START, StateGraph

from app.graph.test_results.nodes import (
    extract_test_results_node,
    load_test_results_node,
    persist_test_results_node,
)
from app.graph.test_results.state import TestResultsState


builder = StateGraph(TestResultsState)
builder.add_node("load_test_results", load_test_results_node)
builder.add_node("extract_test_results", extract_test_results_node)
builder.add_node("persist_test_results", persist_test_results_node)

builder.add_edge(START, "load_test_results")
builder.add_edge("load_test_results", "extract_test_results")
builder.add_edge("extract_test_results", "persist_test_results")
builder.add_edge("persist_test_results", END)

test_results_graph = builder.compile()
