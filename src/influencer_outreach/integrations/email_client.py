
import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from dotenv import load_dotenv


load_dotenv()


EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$"
)


def validate_email_address(email: str) -> bool:
    """Validate the basic format of an email address."""

    if not isinstance(email, str):
        return False

    email = email.strip()

    if not email or len(email) > 254:
        return False

    if any(character.isspace() for character in email):
        return False

    if email.count("@") != 1:
        return False

    local_part, domain = email.rsplit("@", 1)

    if not local_part or len(local_part) > 64:
        return False

    if ".." in local_part or ".." in domain:
        return False

    return bool(EMAIL_PATTERN.fullmatch(email))


def _current_timestamp() -> str:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


class EmailClient:
    """Email client supporting preview, dry-run and optional SMTP."""

    def __init__(self) -> None:
        self.smtp_host = os.getenv(
            "SMTP_HOST",
            "smtp.gmail.com",
        ).strip()

        self.smtp_port = int(
            os.getenv("SMTP_PORT", "587")
        )

        self.smtp_username = os.getenv(
            "SMTP_USERNAME",
            "",
        ).strip()

        self.smtp_password = os.getenv(
            "SMTP_PASSWORD",
            "",
        ).strip()

        dry_run_value = os.getenv(
            "EMAIL_DRY_RUN",
            "True",
        ).strip().lower()

        if dry_run_value not in (
            "true",
            "false",
            "1",
            "0",
            "yes",
            "no",
        ):
            raise ValueError(
                "EMAIL_DRY_RUN must be True or False."
            )

        self.dry_run = dry_run_value in (
            "true",
            "1",
            "yes",
        )

    def _validate_email_content(
        self,
        to_email: str,
        subject: str,
        body: str,
    ) -> None:
        """Validate recipient and email content."""

        if not validate_email_address(to_email):
            raise ValueError(
                "Invalid recipient email address."
            )

        if not isinstance(subject, str) or not subject.strip():
            raise ValueError(
                "Email subject cannot be empty."
            )

        if "\r" in subject or "\n" in subject:
            raise ValueError(
                "Email subject contains invalid characters."
            )

        if not isinstance(body, str) or not body.strip():
            raise ValueError(
                "Email body cannot be empty."
            )

    def preview_email(
        self,
        to_email: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        """Prepare an email preview without sending anything."""

        self._validate_email_content(
            to_email,
            subject,
            body,
        )

        return {
            "recipient": to_email.strip(),
            "subject": subject.strip(),
            "body": body.strip(),
            "preview_created_at": _current_timestamp(),
            "status": "preview",
        }

    def _build_message(
        self,
        to_email: str,
        subject: str,
        body: str,
    ) -> EmailMessage:
        """Build an SMTP email message."""

        if not validate_email_address(self.smtp_username):
            raise ValueError(
                "A valid SMTP_USERNAME is required."
            )

        message = EmailMessage()

        message["From"] = self.smtp_username
        message["To"] = to_email.strip()
        message["Subject"] = subject.strip()

        message.set_content(body.strip())

        return message

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        allow_real_send: bool = False,
    ) -> dict[str, Any]:
        """Simulate or optionally send an email."""

        self._validate_email_content(
            to_email,
            subject,
            body,
        )

        timestamp = _current_timestamp()

        # Dry-run mode: never contact an SMTP server.
        if self.dry_run:
            return {
                "recipient": to_email.strip(),
                "status": "simulated",
                "dry_run": True,
                "sent_at": timestamp,
                "message": (
                    "Email simulated successfully. "
                    "No email was actually sent."
                ),
                "preview": self.preview_email(
                    to_email,
                    subject,
                    body,
                ),
            }

        # Real sending requires explicit approval.
        if not allow_real_send:
            raise PermissionError(
                "Real email sending requires explicit approval."
            )

        if not self.smtp_username or not self.smtp_password:
            raise ValueError(
                "SMTP_USERNAME and SMTP_PASSWORD "
                "must be configured."
            )

        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("Invalid SMTP port.")

        email_message = self._build_message(
            to_email,
            subject,
            body,
        )

        try:
            with smtplib.SMTP(
                self.smtp_host,
                self.smtp_port,
                timeout=20,
            ) as server:

                server.starttls(
                    context=ssl.create_default_context()
                )

                server.login(
                    self.smtp_username,
                    self.smtp_password,
                )

                server.send_message(email_message)

            return {
                "recipient": to_email.strip(),
                "status": "sent",
                "dry_run": False,
                "sent_at": _current_timestamp(),
                "message": "Email sent successfully.",
                "error": None,
            }

        except (smtplib.SMTPException, OSError) as exc:
            return {
                "recipient": to_email.strip(),
                "status": "failed",
                "dry_run": False,
                "sent_at": _current_timestamp(),
                "message": "Email sending failed.",
                "error": str(exc),
            }
