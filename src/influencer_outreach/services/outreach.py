
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.influencer_outreach.integrations.email_client import (
    EmailClient,
    validate_email_address,
)


def _get_default_history_path() -> Path:
    """Return the default outreach history location."""

    project_root = Path(__file__).resolve().parents[3]

    return (
        project_root
        / "data"
        / "processed"
        / "outreach_history.json"
    )


def _load_history(
    history_path: Path,
) -> dict[str, Any]:
    """Load existing outreach history."""

    if not history_path.exists():
        return {"records": []}

    try:
        with history_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Unable to read outreach history."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Invalid outreach history format."
        )

    if not isinstance(data.get("records"), list):
        raise ValueError(
            "Outreach history records must be a list."
        )

    return data


def _save_history(
    history_path: Path,
    history: dict[str, Any],
) -> None:
    """Save outreach history safely."""

    history_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = history_path.with_suffix(".tmp")

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                history,
                file,
                indent=4,
                ensure_ascii=False,
            )

        temporary_path.replace(history_path)

    except OSError as exc:

        if temporary_path.exists():
            temporary_path.unlink()

        raise ValueError(
            "Unable to save outreach history."
        ) from exc


def _normalize_email(email: str) -> str:
    """Normalize an email for duplicate comparison."""

    return email.strip().lower()


def _already_contacted(
    history: dict[str, Any],
    channel_id: str | None,
    email: str,
) -> bool:
    """Check whether an influencer or recipient was contacted."""

    normalized_email = _normalize_email(email)

    for record in history["records"]:

        previous_status = record.get("status")

        if previous_status not in ("simulated", "sent"):
            continue

        previous_channel_id = record.get("channel_id")
        previous_email = record.get("recipient", "")

        if (
            channel_id
            and previous_channel_id == channel_id
        ):
            return True

        if (
            previous_email
            and _normalize_email(previous_email)
            == normalized_email
        ):
            return True

    return False


def _append_history_record(
    history_path: Path,
    record: dict[str, Any],
) -> None:
    """Append one event to persistent outreach history."""

    history = _load_history(history_path)

    history["records"].append(record)

    _save_history(history_path, history)


def preview_influencer_email(
    influencer: dict[str, Any],
    message: dict[str, Any],
) -> dict[str, Any]:
    """Preview a generated email without sending it."""

    if influencer.get("filter_status") != "PASS":
        raise ValueError(
            "Email preview is allowed only for PASS influencers."
        )

    recipient = influencer.get(
        "contact_email",
        "Not Found",
    )

    if not validate_email_address(recipient):
        raise ValueError(
            "Influencer does not have a valid public email."
        )

    client = EmailClient()

    return client.preview_email(
        to_email=recipient,
        subject=message.get("email_subject", ""),
        body=message.get("email_pitch", ""),
    )


def process_email_outreach(
    influencer: dict[str, Any],
    message: dict[str, Any],
    allow_real_send: bool = False,
    history_path: str | Path | None = None,
) -> dict[str, Any]:
    """Process one outreach attempt with duplicate prevention."""

    if influencer.get("filter_status") != "PASS":
        raise ValueError(
            "Outreach is allowed only for PASS influencers."
        )

    destination = (
        Path(history_path)
        if history_path
        else _get_default_history_path()
    )

    history = _load_history(destination)

    channel_id = influencer.get("channel_id")

    influencer_name = influencer.get(
        "influencer_name",
        influencer.get("channel_name", "Unknown"),
    )

    recipient = influencer.get(
        "contact_email",
        "Not Found",
    )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    base_record = {
        "channel_id": channel_id,
        "influencer_name": influencer_name,
        "recipient": recipient,
        "email_subject": message.get(
            "email_subject",
            "",
        ),
        "email_body": message.get(
            "email_pitch",
            "",
        ),
        "processed_at": timestamp,
    }

    # Check for a valid publicly listed email.
    if not validate_email_address(recipient):

        result = {
            **base_record,
            "status": "skipped_no_valid_email",
            "dry_run": True,
            "sent_at": None,
            "error": (
                "No valid publicly listed contact email found."
            ),
        }

        _append_history_record(
            destination,
            result,
        )

        return result

    # Check duplicate channel ID and email.
    if _already_contacted(
        history,
        channel_id,
        recipient,
    ):

        return {
            **base_record,
            "status": "duplicate",
            "dry_run": True,
            "sent_at": None,
            "error": None,
            "message": (
                "Duplicate outreach prevented. "
                "This influencer or email was already contacted."
            ),
        }

    client = EmailClient()

    try:

        email_result = client.send_email(
            to_email=recipient,
            subject=message.get("email_subject", ""),
            body=message.get("email_pitch", ""),
            allow_real_send=allow_real_send,
        )

        result = {
            **base_record,
            "status": email_result["status"],
            "dry_run": email_result["dry_run"],
            "sent_at": email_result.get("sent_at"),
            "error": email_result.get("error"),
            "message": email_result.get("message"),
        }

    except (ValueError, PermissionError) as exc:

        result = {
            **base_record,
            "status": "blocked",
            "dry_run": client.dry_run,
            "sent_at": None,
            "error": str(exc),
        }

    _append_history_record(
        destination,
        result,
    )

    return result


def process_batch_outreach(
    influencers: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    allow_real_send: bool = False,
    history_path: str | Path | None = None,
) -> dict[str, Any]:
    """Process generated email messages for qualified influencers."""

    destination = (
        Path(history_path)
        if history_path
        else _get_default_history_path()
    )

    message_lookup = {}

    for message in messages:

        channel_id = message.get("channel_id")

        if not channel_id:
            continue

        if channel_id in message_lookup:
            raise ValueError(
                "Duplicate personalized messages found."
            )

        message_lookup[channel_id] = message

    qualified = [
        influencer
        for influencer in influencers
        if influencer.get("filter_status") == "PASS"
    ]

    results = []

    for influencer in qualified:

        channel_id = influencer.get("channel_id")

        message = message_lookup.get(channel_id)

        influencer_name = influencer.get(
            "influencer_name",
            influencer.get("channel_name", "Unknown"),
        )

        if not message:

            result = {
                "channel_id": channel_id,
                "influencer_name": influencer_name,
                "recipient": influencer.get(
                    "contact_email",
                    "Not Found",
                ),
                "status": "skipped_no_message",
                "dry_run": True,
                "sent_at": None,
                "processed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "error": (
                    "No personalized email message was found."
                ),
            }

            _append_history_record(
                destination,
                result,
            )

            results.append(result)

            continue

        try:

            result = process_email_outreach(
                influencer=influencer,
                message=message,
                allow_real_send=allow_real_send,
                history_path=destination,
            )

            results.append(result)

        except Exception as exc:

            results.append({
                "channel_id": channel_id,
                "influencer_name": influencer_name,
                "status": "failed",
                "dry_run": True,
                "sent_at": None,
                "processed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "error": str(exc),
            })

    counts = {}

    for result in results:

        status = result["status"]

        counts[status] = counts.get(status, 0) + 1

    return {
        "total_qualified": len(qualified),
        "processed": len(results),
        "status_counts": counts,
        "results": results,
        "history_path": str(destination),
    }


def get_outreach_history(
    history_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return saved outreach history records."""

    destination = (
        Path(history_path)
        if history_path
        else _get_default_history_path()
    )

    history = _load_history(destination)

    return history["records"]
