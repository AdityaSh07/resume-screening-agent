from .document_loader import load_candidates

import re
from langchain_core.documents import Document


URL_PATTERN = re.compile(r"https?://[^\s]+")


def extract_candidate_links(document: Document) -> dict[str, str | None]:
    urls = URL_PATTERN.findall(document.page_content)

    github_url = None
    resume_url = None

    for url in urls:
        url = url.rstrip(".,;:)]}")

        if "github.com" in url.lower():
            github_url = url

        elif (
            "drive.google.com" in url.lower()
            or "docs.google.com" in url.lower()
            or url.lower().endswith(".pdf")
        ):
            resume_url = url

    return {
        "github_url": github_url,
        "resume_url": resume_url,
    }