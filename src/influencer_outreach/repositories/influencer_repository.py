
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Influencer, PersonalizedMessage


def _required_text(record: dict[str, Any], field: str) -> str:
    """Return a required non-empty string field."""
    value = record.get(field)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid required field: {field}")

    return value.strip()


def _parse_datetime(value: Any) -> datetime:
    """Convert a datetime value or ISO-formatted string to datetime."""
    if isinstance(value, datetime):
        return value

    if isinstance(value, str) and value.strip():
        value = value.strip()

        # Support ISO timestamps ending in Z.
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid generated_at timestamp: {value}"
            ) from exc

    raise ValueError("Missing or invalid generated_at timestamp")


def _word_count(text: str) -> int:
    """Calculate the number of words in a message."""
    return len(text.split())


def save_personalized_messages(
    db: Session,
    messages: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Save personalized messages in SQLite.

    A message is associated with an existing influencer using channel_id.
    If that influencer already has a personalized message, the latest
    existing record is updated. Otherwise, a new record is inserted.

    This function flushes changes but does not commit. The caller controls
    the database transaction.
    """
    if not isinstance(messages, list):
        raise TypeError("messages must be a list of dictionaries")

    inserted = 0
    updated = 0
    processed_channel_ids: set[str] = set()

    for index, record in enumerate(messages):
        if not isinstance(record, dict):
            raise TypeError(
                f"Message at index {index} must be a dictionary"
            )

        channel_id = _required_text(record, "channel_id")

        if channel_id in processed_channel_ids:
            raise ValueError(
                f"Duplicate channel_id in input batch: {channel_id}"
            )

        processed_channel_ids.add(channel_id)

        email_subject = _required_text(record, "email_subject")
        email_pitch = _required_text(record, "email_pitch")
        instagram_dm = _required_text(record, "instagram_dm")
        generation_model = _required_text(record, "generation_model")
        generated_at = _parse_datetime(record.get("generated_at"))

        influencer = db.scalar(
            select(Influencer).where(
                Influencer.channel_id == channel_id
            )
        )

        if influencer is None:
            raise ValueError(
                f"Influencer not found in database: {channel_id}"
            )

        email_word_count = record.get("email_word_count")
        if not isinstance(email_word_count, int) or email_word_count < 0:
            email_word_count = _word_count(email_pitch)

        dm_word_count = record.get("instagram_dm_word_count")
        if not isinstance(dm_word_count, int) or dm_word_count < 0:
            dm_word_count = _word_count(instagram_dm)

        generation_attempts = record.get("generation_attempts", 1)
        if not isinstance(generation_attempts, int) or generation_attempts < 1:
            generation_attempts = 1

        generation_status = record.get("generation_status", "success")
        if not isinstance(generation_status, str) or not generation_status.strip():
            generation_status = "success"

        source_evidence = record.get("source_evidence", [])

        existing_message = db.scalar(
            select(PersonalizedMessage)
            .where(
                PersonalizedMessage.influencer_id == influencer.id
            )
            .order_by(PersonalizedMessage.generated_at.desc())
            .limit(1)
        )

        message_data = {
            "email_subject": email_subject,
            "email_pitch": email_pitch,
            "email_word_count": email_word_count,
            "instagram_dm": instagram_dm,
            "instagram_dm_word_count": dm_word_count,
            "generation_status": generation_status.strip(),
            "generation_model": generation_model,
            "generation_attempts": generation_attempts,
            "source_evidence": source_evidence,
            "generated_at": generated_at,
        }

        if existing_message is None:
            new_message = PersonalizedMessage(
                influencer_id=influencer.id,
                **message_data,
            )
            db.add(new_message)
            inserted += 1
        else:
            for field, value in message_data.items():
                setattr(existing_message, field, value)

            updated += 1

    db.flush()

    return {
        "processed": len(messages),
        "inserted": inserted,
        "updated": updated,
    }


def get_personalized_messages(
    db: Session,
    limit: int | None = None,
) -> list[PersonalizedMessage]:
    """Return personalized messages, newest first."""
    statement = select(PersonalizedMessage).order_by(
        PersonalizedMessage.generated_at.desc()
    )

    if limit is not None:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")

        statement = statement.limit(limit)

    return list(db.scalars(statement).all())


def get_messages_by_channel_id(
    db: Session,
    channel_id: str,
) -> list[PersonalizedMessage]:
    """Return all personalized messages for one YouTube channel."""
    if not isinstance(channel_id, str) or not channel_id.strip():
        raise ValueError("channel_id must be a non-empty string")

    influencer = db.scalar(
        select(Influencer).where(
            Influencer.channel_id == channel_id.strip()
        )
    )

    if influencer is None:
        return []

    statement = (
        select(PersonalizedMessage)
        .where(PersonalizedMessage.influencer_id == influencer.id)
        .order_by(PersonalizedMessage.generated_at.desc())
    )

    return list(db.scalars(statement).all())
