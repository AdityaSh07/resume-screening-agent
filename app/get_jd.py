from pathlib import Path
from fastapi import UploadFile
from langchain_community.document_loaders import (
    PyPDFLoader
)


async def process_job_description(
    jd_file: UploadFile | None,
    jd_text: str | None,
) -> str:

    # User provided text
    if jd_text and jd_text.strip():
        return jd_text.strip()

    # User uploaded a file
    if jd_file:

        if jd_file.filename is None:
            raise ValueError("Invalid JD file")

        extension = Path(jd_file.filename).suffix.lower()

        if extension != ".pdf":
            raise ValueError(
                "Only PDF files are supported"
            )

        # Save uploaded file
        file_path = Path("uploads") / jd_file.filename

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(file_path, "wb") as f:
            f.write(await jd_file.read())

        # Extract complete PDF
        documents = PyPDFLoader(
            str(file_path)
        ).load()

        return "\n\n".join(
            document.page_content
            for document in documents
        )

    raise ValueError(
        "Provide either jd_file or jd_text"
    )