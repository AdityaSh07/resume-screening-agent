from __future__ import annotations

import logging

from app.database import (
    get_interview_candidate,
    save_interview_details,
)
from app.services.email_service import email_service
from app.services.calendar_invite_service import create_calendar_invite
from app.services.google_calendar_service import calendar_service
from .state import InterviewState

logger = logging.getLogger(__name__)


async def schedule_interview_node(state: InterviewState) -> dict:
    candidate = await get_interview_candidate(
        state["job_id"], state["candidate_id"]
    )
    if candidate is None:
        return {"error": "Candidate was not found for this job."}
    if candidate.qualification_status != "interview_eligible":
        return {"error": "Candidate is not eligible for an interview."}
    is_legacy_meeting = bool(
        candidate.meeting_url
        and "meet.jit.si" in candidate.meeting_url
    )
    if candidate.meeting_id and not is_legacy_meeting:
        return {
            "candidate": {
                "id": candidate.id,
                "name": candidate.name,
                "email": candidate.email,
                "meeting_id": candidate.meeting_id,
                "meeting_url": candidate.meeting_url,
                "interview_start": candidate.interview_start.isoformat() if candidate.interview_start else None,
                "interview_end": candidate.interview_end.isoformat() if candidate.interview_end else None,
                "interview_timezone": candidate.interview_timezone,
                "interview_status": candidate.interview_status,
            },
            "meeting": {
                "meeting_id": candidate.meeting_id,
                "meeting_url": candidate.meeting_url,
                "provider": "Jitsi Meet",
            },
            "existing_interview": True,
        }
    if not candidate.email:
        return {"error": "Candidate email is missing."}
    return {
        "candidate": {
            "id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
        }
    }


async def create_meeting_node(state: InterviewState) -> dict:
    if state.get("error") or state.get("existing_interview"):
        return {"meeting": state.get("meeting") or {}}
    candidate = state["candidate"]
    try:
        meeting = await calendar_service.create_interview_event(
            candidate_name=candidate["name"],
            candidate_email=candidate["email"],
            interviewer=state.get("interviewer", "Recruitment Team"),
            start=state["interview_start"],
            end=state["interview_end"],
            timezone=state["timezone"],
        )
        return {"meeting": meeting}
    except Exception as exc:
        logger.exception("Meeting creation failed")
        return {"error": f"Meeting creation failed: {str(exc)[:200]}"}


async def create_calendar_invite_node(state: InterviewState) -> dict:
    if state.get("error") or not state.get("meeting"):
        return {"calendar_invite_filename": "", "calendar_invite_content": b""}
    try:
        candidate = state["candidate"]
        filename, content = create_calendar_invite(
            candidate_name=candidate["name"],
            candidate_email=candidate["email"],
            interviewer=state.get("interviewer", "Recruitment Team"),
            start=state["interview_start"],
            end=state["interview_end"],
            timezone=state["timezone"],
            meeting_url=state["meeting"]["meeting_url"],
        )
        return {
            "calendar_invite_filename": filename,
            "calendar_invite_content": content,
        }
    except Exception as exc:
        logger.exception("Calendar invite creation failed")
        return {"error": f"Calendar invite creation failed: {str(exc)[:200]}"}


async def persist_interview_node(state: InterviewState) -> dict:
    if state.get("error") or not state.get("meeting"):
        return {"email_sent": state.get("email_sent", False)}
    meeting = state["meeting"]
    await save_interview_details(
        state["candidate_id"],
        meeting_id=meeting["meeting_id"],
        meeting_url=meeting["meeting_url"],
        start=state["interview_start"],
        end=state["interview_end"],
        timezone=state["timezone"],
        status="email_sent" if state.get("email_sent") else "email_failed",
    )
    return {"email_sent": state.get("email_sent", False)}


async def send_interview_email_node(state: InterviewState) -> dict:
    if state.get("error"):
        return {"email_sent": False}
    candidate = state["candidate"]
    meeting = state.get("meeting")
    if not meeting:
        return {"email_sent": False}
    sent = await email_service.send_interview_invitation(
        to_email=candidate["email"],
        candidate_name=candidate["name"],
        interview_time=state["interview_start"].strftime(
            "%d %B %Y, %I:%M %p"
        ) + f" ({state['timezone']})",
        meet_link=meeting["meeting_url"],
        timezone=state["timezone"],
        calendar_filename=state["calendar_invite_filename"],
        calendar_content=state["calendar_invite_content"],
    )
    return {"email_sent": sent}
