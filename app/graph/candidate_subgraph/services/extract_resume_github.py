import re
from langchain_core.documents import Document


URL_PATTERN = re.compile(r"https?://[^\s]+")


def extract_candidate_links(
    document: Document,
) -> dict[str, str | None]:

    urls = URL_PATTERN.findall(
        document.page_content
    )

    github_url = None
    resume_url = None

    for url in urls:

        # Remove punctuation that may be attached to the URL
        url = url.rstrip(".,;:)]}")

        lower_url = url.lower()

        # GitHub
        if (
            "github.com/" in lower_url
            and github_url is None
        ):
            github_url = url

        # Resume
        elif (
            (
                "drive.google.com/" in lower_url
                or "docs.google.com/" in lower_url
                or lower_url.endswith(".pdf")
            )
            and resume_url is None
        ):
            resume_url = url

    return {
        "github_url": github_url,
        "resume_url": resume_url,
    }