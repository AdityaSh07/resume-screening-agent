from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from app.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_TOKEN_ENCRYPTION_KEY,
)
from app.database import load_google_token, save_google_token

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleCalendarService:
    def _require_config(self) -> None:
        missing = [
            name for name, value in (
                ("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID),
                ("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET),
                ("GOOGLE_REDIRECT_URI", GOOGLE_REDIRECT_URI),
                ("GOOGLE_TOKEN_ENCRYPTION_KEY", GOOGLE_TOKEN_ENCRYPTION_KEY),
            ) if not value
        ]
        if missing:
            raise RuntimeError("Set these values in .env: " + ", ".join(missing))

    def _fernet(self):
        from cryptography.fernet import Fernet
        self._require_config()
        return Fernet(GOOGLE_TOKEN_ENCRYPTION_KEY.encode())

    def _client_config(self) -> dict[str, Any]:
        self._require_config()
        return {"web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }}

    def authorization_url(self) -> str:
        self._require_config()
        query = urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        })
        return "https://accounts.google.com/o/oauth2/v2/auth?" + query

    async def exchange_code(self, code: str) -> None:
        from google_auth_oauthlib.flow import Flow

        self._require_config()

        def exchange() -> dict[str, Any]:
            flow = Flow.from_client_config(self._client_config(), scopes=SCOPES)
            flow.redirect_uri = GOOGLE_REDIRECT_URI
            flow.fetch_token(code=code)
            credentials = flow.credentials
            return {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "scopes": list(credentials.scopes or SCOPES),
            }

        token = await asyncio.to_thread(exchange)
        encrypted = self._fernet().encrypt(json.dumps(token).encode()).decode()
        await save_google_token({"encrypted": encrypted})

    async def _credentials(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        stored = await load_google_token()
        if not stored:
            raise RuntimeError("Google Calendar is not connected.")
        token = json.loads(self._fernet().decrypt(stored["encrypted"].encode()))
        credentials = Credentials(
            token=token.get("token"),
            refresh_token=token.get("refresh_token"),
            token_uri=token.get("token_uri"),
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=token.get("scopes") or SCOPES,
        )
        if credentials.expired and credentials.refresh_token:
            await asyncio.to_thread(credentials.refresh, Request())
            token["token"] = credentials.token
            encrypted = self._fernet().encrypt(json.dumps(token).encode()).decode()
            await save_google_token({"encrypted": encrypted})
        if not credentials.valid:
            raise RuntimeError("Google Calendar authorization is expired or invalid.")
        return credentials

    async def create_interview_event(
        self,
        *,
        candidate_name: str,
        candidate_email: str,
        interviewer: str,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> dict[str, str]:
        from googleapiclient.discovery import build

        credentials = await self._credentials()

        def create() -> dict[str, str]:
            calendar = build("calendar", "v3", credentials=credentials)
            event = calendar.events().insert(
                calendarId="primary",
                conferenceDataVersion=1,
                sendUpdates="all",
                body={
                    "summary": f"AI/ML Engineer Interview - {candidate_name}",
                    "description": f"Interview with {candidate_name}. Interviewer: {interviewer}",
                    "start": {"dateTime": start.isoformat(), "timeZone": timezone},
                    "end": {"dateTime": end.isoformat(), "timeZone": timezone},
                    "attendees": [{"email": candidate_email}],
                    "conferenceData": {
                        "createRequest": {
                            "requestId": f"screeneasy-{candidate_email}-{int(start.timestamp())}",
                            "conferenceSolutionKey": {"type": "hangoutsMeet"},
                        }
                    },
                },
            ).execute()
            meet_url = event.get("hangoutLink")
            if not meet_url:
                for entry in event.get("conferenceData", {}).get("entryPoints", []):
                    if entry.get("entryPointType") == "video":
                        meet_url = entry.get("uri")
                        break
            if not meet_url:
                raise RuntimeError("Google Calendar did not return a Meet link.")
            return {"meeting_id": event["id"], "meeting_url": meet_url, "provider": "Google Calendar"}

        return await asyncio.to_thread(create)


calendar_service = GoogleCalendarService()
