import logging
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.document_loader import ALLOWED_EXTENSIONS
from app.graph.graph import graph


logger = logging.getLogger(__name__)
app = FastAPI(title="ScreenEasy API")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

UPLOAD_DIR = Path("uploads")


def _json_safe(value):
	"""Convert LangChain/Pydantic values into an API response shape."""
	if hasattr(value, "model_dump"):
		return value.model_dump()
	if hasattr(value, "dict"):
		return value.dict()
	if isinstance(value, dict):
		return {key: _json_safe(item) for key, item in value.items()}
	if isinstance(value, list):
		return [_json_safe(item) for item in value]
	if isinstance(value, tuple):
		return [_json_safe(item) for item in value]
	if isinstance(value, (str, int, float, bool)) or value is None:
		return value
	return str(value)


def _result_for_response(result: dict) -> dict:
	ignored_fields = {"candidate", "jd_requirements", "resume_data", "github_text"}
	return {
		key: _json_safe(value)
		for key, value in result.items()
		if key not in ignored_fields
	}


@app.get("/health")
async def health() -> dict[str, str]:
	return {"status": "ok"}


@app.post("/api/screen")
@limiter.limit("1/hour")
async def screen_candidates(
	request: Request,
	candidates_file: UploadFile = File(...),
	jd_text: str = Form(...),
) -> JSONResponse:
	if not candidates_file.filename:
		raise HTTPException(status_code=400, detail="Candidate file is required.")

	extension = Path(candidates_file.filename).suffix.lower()
	if extension not in ALLOWED_EXTENSIONS:
		allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
		raise HTTPException(
			status_code=400,
			detail=f"Unsupported candidate file type. Use: {allowed}.",
		)
	if not jd_text.strip():
		raise HTTPException(status_code=400, detail="Job description is required.")

	UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
	upload_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

	try:
		upload_path.write_bytes(await candidates_file.read())
		workflow_result = await graph.ainvoke(
			{
				"job_id": uuid4().hex,
				"candidates_file_path": str(upload_path),
				"jd_text": jd_text.strip(),
			}
		)
		results = [
			_result_for_response(item)
			for item in workflow_result.get("candidate_results", [])
		]
		shortlisted = [
			_result_for_response(item)
			for item in workflow_result.get("shortlisted_candidates", [])
		]
		return JSONResponse(
			content={
				"total_candidates": len(results),
				"evaluated": len(results),
				"shortlisted": len(shortlisted),
				"candidates": results,
				"shortlisted_candidates": shortlisted,
				"email_results": workflow_result.get("email_results", []),
			}
		)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc
	except Exception:
		logger.exception("Candidate screening workflow failed")
		raise HTTPException(
			status_code=500,
			detail="The screening workflow failed. Check the server logs for details.",
		) from None
	finally:
		upload_path.unlink(missing_ok=True)


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

