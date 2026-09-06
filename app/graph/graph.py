"""
Main screening pipeline graph.

Architecture
------------

    START
      ↓
    load_candidates          — CSV/Excel → list[Document]
      ↓
    process_job_description  — text/PDF → raw JD string
      ↓
    analyze_jd               — LLM: extract structured JD requirements
      ↓
    evaluate_candidates      — sequential batched candidate evaluation
      │  for each batch (default batch_size=1):
      │    invoke candidate_subgraph for each candidate in batch
      │      ├── extract_links     (no LLM)
      │      ├── download_resume   (no LLM)
      │      ├── resume_eval       (LLM — rate-limiter protected)
      │      ├── analyze_github    (no LLM — GitHub API)
      │      └── github_eval       (LLM — rate-limiter protected)
      │    wait LLM_BATCH_WAIT_SECONDS between batches
      ↓
    rank_candidates           — sort by score, populate shortlisted_candidates
      ↓
    send_shortlisted_test_emails — email assessment links to shortlisted candidates
      ↓
    END

Rate-limiting note
------------------
The `Send` fan-out previously used here dispatched ALL candidates
concurrently, causing 429 / rate-limit errors on the Groq API
(~8 000 TPM limit).

The new `evaluate_candidates` node processes candidates in batches of
`LLM_BATCH_SIZE` (default 1) with a `LLM_BATCH_WAIT_SECONDS` (default
60 s) pause between batches so the provider's TPM window can reset.
Additionally, each LLM call inside the subgraph acquires a token slot
from the shared `llm_rate_limiter` before firing.
"""

from langgraph.graph import START, END

from .state import ScreeningState
from .nodes import builder


builder.add_edge(START, "load_candidates")
builder.add_edge("load_candidates", "process_job_description")
builder.add_edge("process_job_description", "analyze_jd")
builder.add_edge("analyze_jd", "evaluate_candidates")
builder.add_edge("evaluate_candidates", "rank_candidates")
builder.add_edge("rank_candidates", "send_shortlisted_test_emails")
builder.add_edge("send_shortlisted_test_emails", END)


graph = builder.compile()
