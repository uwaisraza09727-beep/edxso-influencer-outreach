
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.influencer_outreach.models import (
    Influencer,
    OutreachRecord,
    PersonalizedMessage,
)


def _word_count(value: str) -> int:
    """Return the number of words in a message."""
    return len(value.split()) if value else 0


def save_personalized_messages(
    db: Session,
    messages: list[dict[str, Any]],
) -> dict[str, int]:
    """Save or update personalized messages for existing influencers."""
    inserted = 0
    updated = 0
    skipped = 0
    processed_channel_ids = set()

    for record in messages:
        channel_id = str(record.get("channel_id", "")).strip()

        if not channel_id:
            raise ValueError("Personalized message is missing channel_id.")

        if channel_id in processed_channel_ids:
            raise ValueError(f"Duplicate channel_id: {channel_id}")

        processed_channel_ids.add(channel_id)

        email_subject = str(record.get("email_subject", "")).strip()
        email_pitch = str(record.get("email_pitch", "")).strip()
        instagram_dm = str(record.get("instagram_dm", "")).strip()

        if not email_subject or not email_pitch or not instagram_dm:
            raise ValueError(
                f"Incomplete personalized message for {channel_id}."
            )

        influencer = db.scalar(
            select(Influencer).where(
                Influencer.channel_id == channel_id
            )
        )

        if influencer is None:
            skipped += 1
            continue

        existing = db.scalar(
            select(PersonalizedMessage)
            .where(PersonalizedMessage.influencer_id == influencer.id)
            .order_by(PersonalizedMessage.id.desc())
        )

        generated_at = record.get("generated_at")
        if isinstance(generated_at, str):
            generated_at = datetime.fromisoformat(
                generated_at.replace("Z", "+00:00")
            )

        if generated_at is None:
            generated_at = datetime.now(timezone.utc)

        message_data = {
            "email_subject": email_subject,
            "email_pitch": email_pitch,
            "email_word_count": record.get(
                "email_word_count", _word_count(email_pitch)
            ),
            "instagram_dm": instagram_dm,
            "instagram_dm_word_count": record.get(
                "instagram_dm_word_count", _word_count(instagram_dm)
            ),
            "generation_status": record.get(
                "generation_status", "success"
            ),
            "generation_model": record.get(
                "generation_model", "unknown"
            ),
            "generation_attempts": record.get("generation_attempts", 1),
            "source_evidence": record.get("source_evidence", {}),
            "generated_at": generated_at,
        }

        if existing is not None:
            for field, value in message_data.items():
                setattr(existing, field, value)
            updated += 1
        else:
            db.add(
                PersonalizedMessage(
                    influencer_id=influencer.id,
                    **message_data,
                )
            )
            inserted += 1

    db.flush()

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "total_processed": len(messages),
    }


def get_personalized_messages(
    db: Session,
) -> list[PersonalizedMessage]:
    """Return all personalized messages."""
    statement = select(PersonalizedMessage).order_by(
        PersonalizedMessage.generated_at.desc()
    )
    return list(db.scalars(statement).all())


def get_messages_by_channel_id(
    db: Session,
    channel_id: str,
) -> list[PersonalizedMessage]:
    """Return personalized messages for one channel."""
    statement = (
        select(PersonalizedMessage)
        .join(Influencer)
        .where(Influencer.channel_id == channel_id)
        .order_by(PersonalizedMessage.generated_at.desc())
    )
    return list(db.scalars(statement).all())


def save_outreach_records(
    db: Session,
    records: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Save or update outreach history.

    Missing email addresses are preserved as Not Found.
    An internal channel-specific identifier is used for
    database duplicate prevention when no email exists.

    The caller is responsible for committing or rolling back.
    """
    inserted = 0
    updated = 0
    skipped = 0
    processed_keys = set()

    for record in records:
        channel_id = str(record.get("channel_id", "")).strip()

        if not channel_id:
            raise ValueError("Outreach record is missing channel_id.")

        influencer = db.scalar(
            select(Influencer).where(
                Influencer.channel_id == channel_id
            )
        )

        if influencer is None:
            skipped += 1
            continue

        recipient = str(record.get("recipient") or "Not Found").strip()

        if not recipient:
            recipient = "Not Found"

        if recipient.lower() in {"not found", "not available", "none"}:
            recipient_email = "Not Found"
            normalized_email = f"__not_found__:{channel_id}"
        else:
            recipient_email = recipient
            normalized_email = recipient.lower()

        duplicate_key = (channel_id, normalized_email)

        if duplicate_key in processed_keys:
            raise ValueError(
                f"Duplicate outreach record in input: {channel_id}"
            )

        processed_keys.add(duplicate_key)

        email_subject = str(
            record.get("email_subject") or ""
        ).strip()

        email_body = str(
            record.get("email_body") or ""
        ).strip()

        status = str(record.get("status") or "unknown").strip()

        if not email_subject or not email_body:
            raise ValueError(
                f"Missing email subject/body for {channel_id}."
            )

        processed_at = record.get("processed_at")
        if not processed_at:
            processed_at = datetime.now(timezone.utc).isoformat()

        sent_at = record.get("sent_at")
        error = record.get("error")
        dry_run = bool(record.get("dry_run", True))

        personalized_message = db.scalar(
            select(PersonalizedMessage)
            .where(PersonalizedMessage.influencer_id == influencer.id)
            .order_by(PersonalizedMessage.id.desc())
        )

        existing = db.scalar(
            select(OutreachRecord).where(
                OutreachRecord.influencer_id == influencer.id,
                OutreachRecord.normalized_recipient_email
                == normalized_email,
            )
        )

        outreach_data = {
            "personalized_message_id": (
                personalized_message.id
                if personalized_message is not None
                else None
            ),
            "recipient_email": recipient_email,
            "normalized_recipient_email": normalized_email,
            "email_subject": email_subject,
            "email_body": email_body,
            "status": status,
            "dry_run": dry_run,
            "sent_at": sent_at,
            "processed_at": str(processed_at),
            "error": error,
            "message": record.get("message"),
        }

        if existing is not None:
            for field, value in outreach_data.items():
                setattr(existing, field, value)
            updated += 1
        else:
            db.add(
                OutreachRecord(
                    influencer_id=influencer.id,
                    **outreach_data,
                )
            )
            inserted += 1

    db.flush()

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "total_processed": len(records),
    }


def get_outreach_records(
    db: Session,
) -> list[OutreachRecord]:
    """Return all outreach records, newest first."""
    statement = select(OutreachRecord).order_by(
        OutreachRecord.processed_at.desc()
    )
    return list(db.scalars(statement).all())


def get_outreach_by_channel_id(
    db: Session,
    channel_id: str,
) -> list[OutreachRecord]:
    """Return outreach history for one influencer."""
    statement = (
        select(OutreachRecord)
        .join(Influencer)
        .where(Influencer.channel_id == channel_id)
        .order_by(OutreachRecord.processed_at.desc())
    )
    return list(db.scalars(statement).all())
