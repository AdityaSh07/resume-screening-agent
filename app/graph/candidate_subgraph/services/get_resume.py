import gdown
from pathlib import Path
from uuid import uuid4


RESUME_DIR = Path("resumes")
RESUME_DIR.mkdir(parents=True, exist_ok=True)


def download_resume(resume_url: str | None) -> str | None:
    if not resume_url:
        return None

    file_path = RESUME_DIR / f"{uuid4().hex}.pdf"

    try:
        result = gdown.download(
            url=resume_url,
            output=str(file_path),
            quiet=True,
        )

        if result is None:
            return None

        if not file_path.exists():
            return None

        if file_path.stat().st_size == 0:
            file_path.unlink()
            return None

        return str(file_path)

    except Exception:
        if file_path.exists():
            file_path.unlink()

        return None