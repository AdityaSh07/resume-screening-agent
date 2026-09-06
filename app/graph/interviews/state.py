from datetime import datetime
from typing import TypedDict


class InterviewState(TypedDict, total=False):
    job_id: str
    candidate_id: int
    interview_start: datetime
    interview_end: datetime
    timezone: str
    interviewer: str
    candidate: dict
    meeting: dict
    calendar_invite_filename: str
    calendar_invite_content: bytes
    existing_interview: bool
    email_sent: bool
    error: str
