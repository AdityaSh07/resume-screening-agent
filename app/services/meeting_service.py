from __future__ import annotations

import secrets
from datetime import datetime


class MeetingService:
    """Creates provider-neutral meeting rooms without Google dependencies."""

    def create_meeting(
        self,
        *,
        candidate_name: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, str]:
        meeting_id = secrets.token_urlsafe(18)
        return {
            "meeting_id": meeting_id,
            "meeting_url": f"https://meet.jit.si/screeneasy-{meeting_id}",
            "provider": "Jitsi Meet",
        }


meeting_service = MeetingService()