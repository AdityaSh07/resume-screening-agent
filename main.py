import logging
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.document_loader import ALLOWED_EXTENSIONS
from app.config import TEST_PASSING_SCORE
from app.graph.graph import graph
from app.graph.test_results.graph import test_results_graph
from app.graph.interviews.graph import interview_graph
from app.database import (
	get_job,
	get_latest_job,
	get_shortlisted_candidates,
	load_google_token,
)
from app.services.google_calendar_service import calendar_service


logger = logging.getLogger(__name__)
app = FastAPI(title="ScreenEasy API")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

UPLOAD_DIR = Path("uploads")


class InterviewScheduleRequest(BaseModel):
	job_id: str
	candidate_id: int
	interview_date: str
	interview_time: str
	duration_minutes: int = 60
	timezone: str
	interviewer: str


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


def _unique_candidate_results(results: list[dict]) -> list[dict]:
	unique: list[dict] = []
	seen: set[str] = set()
	for result in results:
		candidate = result.get("candidate") or {}
		if isinstance(candidate, dict):
			content = candidate.get("page_content", "")
			metadata = candidate.get("metadata", {}) or {}
			key = (
				metadata.get("email")
				or metadata.get("candidate_id")
				or content
			)
		else:
			key = getattr(candidate, "page_content", "")
		if not key:
			key = "|".join(
				str(result.get(field, ""))
				for field in ("name", "email", "overall_score")
			)
		if key in seen:
			continue
		seen.add(key)
		unique.append(result)
	return unique


@app.get("/health")
async def health() -> dict[str, str]:
	return {"status": "ok"}


@app.get("/api/jobs/latest")
async def get_latest_job_details() -> JSONResponse:
	job = await get_latest_job()
	if job is None:
		raise HTTPException(status_code=404, detail="No saved jobs found.")
	job["shortlisted_candidates"] = await get_shortlisted_candidates(job["job_id"])
	return JSONResponse(content=_json_safe(job))


@app.get("/api/jobs/{job_id}")
async def get_job_details(job_id: str) -> JSONResponse:
	job_id = job_id.strip()
	job = await get_job(job_id)
	if job is None:
		raise HTTPException(status_code=404, detail="Job not found.")
	job["shortlisted_candidates"] = await get_shortlisted_candidates(job_id)
	return JSONResponse(content=_json_safe(job))


@app.get("/api/candidates")
async def get_candidates(job_id: str) -> JSONResponse:
	job_id = job_id.strip()
	if not job_id:
		raise HTTPException(status_code=400, detail="job_id is required.")
	if await get_job(job_id) is None:
		raise HTTPException(status_code=404, detail="Job not found.")
	return JSONResponse(
		content={"job_id": job_id, "candidates": await get_shortlisted_candidates(job_id)}
	)


@app.get("/api/dashboard/stats")
async def get_dashboard_stats(job_id: str) -> JSONResponse:
	job_id = job_id.strip()
	if not job_id:
		raise HTTPException(status_code=400, detail="job_id is required.")
	job = await get_job(job_id)
	if job is None:
		raise HTTPException(status_code=404, detail="Job not found.")
	candidates = await get_shortlisted_candidates(job_id)
	return JSONResponse(
		content={
			"total_candidates": len(candidates),
			"evaluated": len(candidates),
			"shortlisted": len(candidates),
			"test_sent": len(candidates),
			"job": {"job_id": job["job_id"], "description": job["jd_text"]},
		}
	)


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
		raw_results = workflow_result.get("candidate_results", [])
		unique_results = _unique_candidate_results(raw_results)
		results = [
			_result_for_response(item)
			for item in unique_results
		]
		shortlisted = [
			_result_for_response(item)
			for item in workflow_result.get("shortlisted_candidates", [])
		]
		return JSONResponse(
			content={
				"job_id": workflow_result.get("job_id"),
				"total_candidates": len(results),
				"evaluated": len(results),
				"shortlisted": len(shortlisted),
				"candidates": results,
				"shortlisted_candidates": shortlisted,
				"email_results": workflow_result.get("email_results", []),
				"database_results": workflow_result.get("database_results", []),
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


@app.post("/api/upload-test-results")
async def upload_test_results(
	file: UploadFile = File(...),
	job_id: str = Form(...),
) -> JSONResponse:
	if not file.filename:
		raise HTTPException(status_code=400, detail="Test-results file is required.")

	extension = Path(file.filename).suffix.lower()
	if extension not in ALLOWED_EXTENSIONS:
		allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
		raise HTTPException(
			status_code=400,
			detail=f"Unsupported test-results file type. Use: {allowed}.",
		)
	if not job_id.strip():
		raise HTTPException(status_code=400, detail="job_id is required.")
	if await get_job(job_id.strip()) is None:
		raise HTTPException(status_code=404, detail="Job not found for this job_id.")

	UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
	upload_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"

	try:
		upload_path.write_bytes(await file.read())
		workflow_result = await test_results_graph.ainvoke(
			{
				"job_id": job_id.strip(),
				"test_results_file_path": str(upload_path),
			}
		)
		results = workflow_result.get("persisted_results", [])
		return JSONResponse(
			content={
				"job_id": job_id.strip(),
				"processed": len(results),
				"updated": sum(item.get("status") == "updated" for item in results),
				"not_found": sum(item.get("status") == "not_found" for item in results),
				"ambiguous": sum(item.get("status") == "ambiguous" for item in results),
				"test_passing_score": TEST_PASSING_SCORE,
				"initial_shortlist_count": workflow_result.get("initial_shortlist_count", 0),
				"matched_count": workflow_result.get("matched_count", 0),
				"final_shortlist_count": workflow_result.get("final_shortlist_count", 0),
				"final_shortlist": [
					_json_safe(item)
					for item in results
					if item.get("qualification_status") == "interview_eligible"
				],
				"results": [_json_safe(item) for item in results],
			}
		)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc
	except Exception:
		logger.exception("Test-results upload workflow failed")
		raise HTTPException(
			status_code=500,
			detail="The test-results workflow failed. Check the server logs for details.",
		) from None
	finally:
		upload_path.unlink(missing_ok=True)


@app.post("/api/interviews/schedule")
async def schedule_interview(request: InterviewScheduleRequest) -> JSONResponse:
	if not request.job_id.strip():
		raise HTTPException(status_code=400, detail="job_id is required.")
	if request.duration_minutes <= 0:
		raise HTTPException(status_code=400, detail="duration_minutes must be positive.")
	try:
		zone = ZoneInfo(request.timezone)
		start = datetime.fromisoformat(
			f"{request.interview_date}T{request.interview_time}"
		).replace(tzinfo=zone)
	except (ValueError, KeyError) as exc:
		raise HTTPException(
			status_code=400,
			detail="Use valid interview_date, interview_time, and IANA timezone values.",
		) from exc

	workflow_result = await interview_graph.ainvoke(
		{
			"job_id": request.job_id.strip(),
			"candidate_id": request.candidate_id,
			"interview_start": start,
			"interview_end": start + timedelta(minutes=request.duration_minutes),
			"timezone": request.timezone,
			"interviewer": request.interviewer.strip(),
		}
	)
	if workflow_result.get("error"):
		raise HTTPException(status_code=400, detail=workflow_result["error"])
	if workflow_result.get("existing_interview") and workflow_result.get("email_sent"):
		return JSONResponse(
			content={
				"status": "already_scheduled",
				"candidate": _json_safe(workflow_result["candidate"]),
			}
		)
	if not workflow_result.get("meeting"):
		raise HTTPException(status_code=502, detail="Interview meeting was not created.")
	if not workflow_result.get("email_sent"):
		raise HTTPException(
			status_code=502,
			detail=(
				"Meeting was created, but Resend did not accept the interview email. "
				"Check RESEND_API_KEY and EMAIL_FROM, then retry scheduling."
			),
		)
	return JSONResponse(
		content={
			"status": "scheduled",
			"meeting": _json_safe(workflow_result["meeting"]),
			"calendar_invite": workflow_result.get("calendar_invite_filename"),
			"email_sent": workflow_result.get("email_sent", False),
		}
	)


@app.get("/api/google-calendar/status")
async def google_calendar_status() -> dict[str, bool]:
	return {"connected": await load_google_token() is not None}


@app.get("/api/google-calendar/connect")
async def connect_google_calendar() -> RedirectResponse:
	try:
		return RedirectResponse(calendar_service.authorization_url())
	except RuntimeError as exc:
		raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/google-calendar/callback", response_model=None)
async def google_calendar_callback(
	code: str | None = None,
	error: str | None = None,
) -> JSONResponse | RedirectResponse:
	if error:
		raise HTTPException(status_code=400, detail=f"Google OAuth failed: {error}")
	if not code:
		raise HTTPException(status_code=400, detail="Google OAuth code is missing.")
	try:
		await calendar_service.exchange_code(code)
		return RedirectResponse(url="/?calendar_connected=1", status_code=303)
	except Exception as exc:
		logger.exception("Google OAuth callback failed")
		raise HTTPException(status_code=400, detail="Google Calendar authorization failed.") from exc


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

