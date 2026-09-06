"""
Email service using the Resend API.

All configuration is read from environment variables.
The API key is NEVER logged, printed, or included in error messages.

Usage
-----
    from app.services.email_service import email_service

    success = await email_service.send_test_invitation(
        to_email="candidate@example.com",
        candidate_name="Jane Doe",
        test_link="https://tests.example.com/abc123",
    )

Environment variables
---------------------
    RESEND_API_KEY   — required, your Resend secret key
    EMAIL_FROM       — optional, defaults to amssre.15001@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import EMAIL_FROM, RESEND_API_KEY

logger = logging.getLogger(__name__)


class EmailService:
    """
    Thin wrapper around the Resend API.

    Attributes
    ----------
    _api_key : str | None
        The Resend API key, read from env. Never exposed in logs.
    _from_address : str
        The sender email address.
    _resend : module | None
        The `resend` Python package, imported lazily so the app
        does not crash if the package is not installed in environments
        that don't need email.
    """

    def __init__(self) -> None:
        self._api_key: str | None = RESEND_API_KEY
        self._from_address: str = EMAIL_FROM
        self._resend: Any = None

        if not self._api_key:
            logger.warning(
                "RESEND_API_KEY is not set. "
                "Email sending will be disabled."
            )

    def _get_resend(self) -> Any:
        """Lazily import and configure the resend package."""
        if self._resend is not None:
            return self._resend

        try:
            import resend as _resend_pkg

            _resend_pkg.api_key = self._api_key
            self._resend = _resend_pkg
            return self._resend

        except ImportError:
            logger.error(
                "The 'resend' package is not installed. "
                "Run: pip install resend"
            )
            return None

    def _is_configured(self) -> bool:
        if not self._api_key:
            logger.warning(
                "Email sending skipped: RESEND_API_KEY not configured."
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_test_invitation(
        self,
        to_email: str,
        candidate_name: str,
        test_link: str,
    ) -> bool:
        """
        Send a test-invitation email to a shortlisted candidate.

        Parameters
        ----------
        to_email : str
            Recipient email address.
        candidate_name : str
            Candidate's display name.
        test_link : str
            URL of the online assessment.

        Returns
        -------
        bool
            True if the email was accepted by Resend, False otherwise.
        """
        if not self._is_configured():
            return False

        resend = self._get_resend()
        if resend is None:
            return False

        subject = "You've been shortlisted! Complete your technical assessment"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Congratulations, {candidate_name}!</h2>
            <p>
                We are pleased to inform you that you have been shortlisted
                for the next stage of our recruitment process.
            </p>
            <p>
                Please complete the technical assessment at the link below.
                The test includes logical aptitude and coding sections.
            </p>
            <p style="text-align: center; margin: 32px 0;">
                <a href="{test_link}"
                   style="background-color: #4F46E5; color: white;
                          padding: 14px 28px; text-decoration: none;
                          border-radius: 6px; font-size: 16px;">
                    Start Assessment
                </a>
            </p>
            <p style="color: #666; font-size: 13px;">
                If the button does not work, copy and paste this link:<br>
                <a href="{test_link}">{test_link}</a>
            </p>
            <p>Good luck!<br>The Recruitment Team</p>
        </div>
        """

        return await self._send(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
        )

    async def send_interview_invitation(
        self,
        to_email: str,
        candidate_name: str,
        interview_time: str,
        meet_link: str,
        interviewer_name: str = "The Interview Panel",
    ) -> bool:
        """
        Send an interview invitation with a Google Meet link.

        Parameters
        ----------
        to_email : str
            Recipient email address.
        candidate_name : str
            Candidate's display name.
        interview_time : str
            Human-readable date/time string (e.g. "Monday 9 Sept at 10:00 AM IST").
        meet_link : str
            Google Meet URL generated by Google Calendar.
        interviewer_name : str
            Name or title of the interviewer(s).

        Returns
        -------
        bool
            True if accepted by Resend, False otherwise.
        """
        if not self._is_configured():
            return False

        resend = self._get_resend()
        if resend is None:
            return False

        subject = f"Interview Invitation — {interview_time}"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Interview Invitation</h2>
            <p>Dear {candidate_name},</p>
            <p>
                We are delighted to invite you to an interview as part of
                our recruitment process.
            </p>
            <table style="width: 100%; border-collapse: collapse;
                          margin: 24px 0; background: #f9f9f9;
                          border-radius: 8px; padding: 16px;">
                <tr>
                    <td style="padding: 8px 16px; font-weight: bold;">Date &amp; Time</td>
                    <td style="padding: 8px 16px;">{interview_time}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 16px; font-weight: bold;">Format</td>
                    <td style="padding: 8px 16px;">Google Meet (video call)</td>
                </tr>
                <tr>
                    <td style="padding: 8px 16px; font-weight: bold;">Interviewer(s)</td>
                    <td style="padding: 8px 16px;">{interviewer_name}</td>
                </tr>
            </table>
            <p style="text-align: center; margin: 32px 0;">
                <a href="{meet_link}"
                   style="background-color: #059669; color: white;
                          padding: 14px 28px; text-decoration: none;
                          border-radius: 6px; font-size: 16px;">
                    Join Google Meet
                </a>
            </p>
            <p style="color: #666; font-size: 13px;">
                Meet link: <a href="{meet_link}">{meet_link}</a>
            </p>
            <p>
                Please confirm your attendance by replying to this email.
                We look forward to speaking with you!
            </p>
            <p>Best regards,<br>The Recruitment Team</p>
        </div>
        """

        return await self._send(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
    ) -> bool:
        """
        Low-level send. Handles errors without leaking the API key.
        """
        resend = self._get_resend()
        if resend is None:
            return False

        try:
            params: dict[str, Any] = {
                "from": self._from_address,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            }

            response = resend.Emails.send(params)

            email_id = (
                response.get("id")
                if isinstance(response, dict)
                else getattr(response, "id", None)
            )

            logger.info(
                "Email sent to %s (id=%s subject=%r)",
                to_email,
                email_id,
                subject,
            )
            return True

        except Exception as exc:
            # Log the error type and a sanitized message.
            # Never log self._api_key or any secret.
            exc_type = type(exc).__name__
            exc_msg = str(exc)

            # Strip potential key leakage patterns just in case
            if self._api_key and self._api_key in exc_msg:
                exc_msg = exc_msg.replace(
                    self._api_key, "[REDACTED]"
                )

            logger.error(
                "Failed to send email to %s (%s): %s",
                to_email,
                exc_type,
                exc_msg[:300],
            )
            return False


# Module-level singleton — import this everywhere
email_service = EmailService()

