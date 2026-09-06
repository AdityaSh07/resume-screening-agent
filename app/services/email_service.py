from __future__ import annotations

import base64
import logging
from typing import Any

from app.config import EMAIL_FROM, EMAIL_REPLY_TO, RESEND_API_KEY

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        self._api_key: str | None = RESEND_API_KEY
        self._from_address = EMAIL_FROM
        self._resend: Any = None
        if not self._api_key:
            logger.warning("RESEND_API_KEY is not set. Email sending is disabled.")

    def _get_resend(self) -> Any:
        if self._resend is not None:
            return self._resend
        try:
            import resend as resend_package
            resend_package.api_key = self._api_key
            self._resend = resend_package
            return resend_package
        except ImportError:
            logger.error("The 'resend' package is not installed.")
            return None

    def _is_configured(self) -> bool:
        if not self._api_key:
            logger.warning("Email sending skipped: RESEND_API_KEY not configured.")
            return False
        return True

    async def send_test_invitation(
        self,
        to_email: str,
        candidate_name: str,
        test_link: str,
    ) -> bool:
        if not self._is_configured():
            return False
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Congratulations, {candidate_name}!</h2>
            <p>You have been shortlisted for the next stage of recruitment.</p>
            <p><a href="{test_link}">Start Assessment</a></p>
        </div>
        """
        return await self._send(
            to_email=to_email,
            subject="You've been shortlisted! Complete your technical assessment",
            html_body=html_body,
        )

    async def send_interview_invitation(
        self,
        to_email: str,
        candidate_name: str,
        interview_time: str,
        meet_link: str,
        interviewer_name: str = "The Interview Panel",
        timezone: str = "UTC",
        calendar_filename: str | None = None,
        calendar_content: bytes | None = None,
    ) -> bool:
        if not self._is_configured():
            return False
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Interview Invitation</h2>
            <p>Dear {candidate_name},</p>
            <p>Your interview has been scheduled.</p>
            <p><strong>Date and time:</strong> {interview_time}<br>
               <strong>Timezone:</strong> {timezone}<br>
               <strong>Interviewer:</strong> {interviewer_name}</p>
            <p><a href="{meet_link}">Join the interview</a></p>
            <p>The attached calendar invite contains the appointment details.</p>
        </div>
        """
        attachments = None
        if calendar_filename and calendar_content:
            attachments = [{
                "filename": calendar_filename,
                "content": base64.b64encode(calendar_content).decode("ascii"),
            }]
        return await self._send(
            to_email=to_email,
            subject=f"Interview Invitation - {interview_time}",
            html_body=html_body,
            attachments=attachments,
        )

    async def _send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> bool:
        resend = self._get_resend()
        if resend is None:
            return False
        params: dict[str, Any] = {
            "from": self._from_address,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        if EMAIL_REPLY_TO:
            params["reply_to"] = EMAIL_REPLY_TO
        if attachments:
            params["attachments"] = attachments
        try:
            response = resend.Emails.send(params)
            email_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
            logger.info("Email sent to %s (id=%s)", to_email, email_id)
            return True
        except Exception as exc:
            message = str(exc)
            if self._api_key:
                message = message.replace(self._api_key, "[REDACTED]")
            logger.error("Failed to send email to %s (%s): %s", to_email, type(exc).__name__, message)
            return False


email_service = EmailService()
