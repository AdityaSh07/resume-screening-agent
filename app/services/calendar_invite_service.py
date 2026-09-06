from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone as utc_timezone


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _utc_stamp(value: datetime) -> str:
    return value.astimezone(utc_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_calendar_invite(
    *,
    candidate_name: str,
    candidate_email: str,
    interviewer: str,
    start: datetime,
    end: datetime,
    timezone: str,
    meeting_url: str,
) -> tuple[str, bytes]:
    uid = f"{uuid.uuid4()}@screeneasy"
    description = (
        f"Interview with {candidate_name}.\\n"
        f"Join the meeting: {meeting_url}\\n"
        "Please join a few minutes early."
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ScreenEasy//Interview//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_utc_stamp(datetime.now(start.tzinfo))}",
        f"DTSTART;TZID={_escape(timezone)}:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID={_escape(timezone)}:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_escape('AI/ML Engineer Interview - ' + candidate_name)}",
        f"ORGANIZER;CN={_escape(interviewer)}:mailto:{_escape(interviewer)}",
        f"ATTENDEE;CN={_escape(candidate_name)};RSVP=TRUE:mailto:{_escape(candidate_email)}",
        f"LOCATION:{_escape(meeting_url)}",
        f"DESCRIPTION:{description}",
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    filename = f"interview-{hashlib.sha256(uid.encode()).hexdigest()[:16]}.ics"
    return filename, "\r\n".join(lines).encode("utf-8")
