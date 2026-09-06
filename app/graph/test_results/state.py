from typing import TypedDict

from langchain_core.documents import Document


class TestResultsState(TypedDict, total=False):
    job_id: str
    test_results_file_path: str
    test_documents: list[Document]
    extracted_results: list[dict]
    persisted_results: list[dict]
    initial_shortlist_count: int
    matched_count: int
    final_shortlist_count: int
