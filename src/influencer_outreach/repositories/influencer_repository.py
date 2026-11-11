
from math import isfinite
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Influencer,
    InfluencerVideo,
    InfluencerEnrichment,
    FilteringResult,
)


def _required_text(record: dict[str, Any], field: str) -> str:
    """Return a required non-empty string."""
    value = record.get(field)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid field: {field}")

    return value.strip()


def _optional_text(value: Any) -> str | None:
    """Return a cleaned optional string."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Expected a string or None.")

    return value.strip() or None


def _to_optional_int(value: Any) -> int | None:
    """Convert a value to integer without inventing missing data."""
    if value is None or isinstance(value, bool):
        return None

    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _to_optional_float(value: Any) -> float | None:
    """Convert a value to a finite float."""
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _json_list(value: Any, field: str) -> list:
    """Validate a JSON list field."""
    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list.")

    return value


def _json_dict(value: Any, field: str) -> dict:
    """Validate a JSON dictionary field."""
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a dictionary.")

    return value


def _validate_influencer_record(
    record: dict[str, Any],
) -> None:
    """Validate a discovery record before saving."""
    if not isinstance(record, dict):
        raise TypeError("Influencer record must be a dictionary.")

    _required_text(record, "channel_id")
    _required_text(record, "channel_name")
    _required_text(record, "profile_url")
    _required_text(record, "retrieved_at")

    _json_list(record.get("matched_keywords"), "matched_keywords")

    videos = record.get("recent_videos", [])

    if not isinstance(videos, list):
        raise ValueError("recent_videos must be a list.")


def _upsert_influencer(
    db: Session,
    record: dict[str, Any],
) -> tuple[Influencer, bool]:
    """Insert a new influencer or update an existing channel."""
    channel_id = _required_text(record, "channel_id")

    influencer = db.scalar(
        select(Influencer).where(
            Influencer.channel_id == channel_id
        )
    )

    values = {
        "channel_name": _required_text(record, "channel_name"),
        "platform": record.get("platform") or "YouTube",
        "profile_url": _required_text(record, "profile_url"),
        "custom_url": _optional_text(record.get("custom_url")),
        "description": record.get("description") or "",
        "channel_country": _optional_text(
            record.get("channel_country")
        ),
        "channel_country_note": _optional_text(
            record.get("channel_country_note")
        ),
        "channel_created_at": _optional_text(
            record.get("channel_created_at")
        ),
        "subscriber_count": _to_optional_int(
            record.get("subscriber_count")
        ),
        "subscriber_count_status": (
            record.get("subscriber_count_status") or "not_returned"
        ),
        "total_views": _to_optional_int(record.get("total_views")),
        "video_count": _to_optional_int(record.get("video_count")),
        "uploads_playlist_id": _optional_text(
            record.get("uploads_playlist_id")
        ),
        "matched_keywords": _json_list(
            record.get("matched_keywords"),
            "matched_keywords",
        ),
        "source": record.get("source") or "YouTube Data API v3",
        "retrieved_at": _required_text(record, "retrieved_at"),
    }

    if influencer is None:
        influencer = Influencer(
            channel_id=channel_id,
            **values,
        )
        db.add(influencer)
        db.flush()
        return influencer, True

    for field, value in values.items():
        setattr(influencer, field, value)

    db.flush()

    return influencer, False


def _upsert_video(
    db: Session,
    influencer_id: int,
    record: dict[str, Any],
) -> bool:
    """Insert a new video or update an existing video."""
    if not isinstance(record, dict):
        raise TypeError("Video record must be a dictionary.")

    video_id = _required_text(record, "video_id")

    values = {
        "title": _required_text(record, "title"),
        "description": record.get("description") or "",
        "published_at": _optional_text(record.get("published_at")),
        "video_url": _required_text(record, "video_url"),
        "view_count": _to_optional_int(record.get("view_count")),
        "like_count": _to_optional_int(record.get("like_count")),
        "comment_count": _to_optional_int(
            record.get("comment_count")
        ),
        "retrieved_at": _required_text(record, "retrieved_at"),
        "source": record.get("source") or "YouTube Data API v3",
    }

    video = db.scalar(
        select(InfluencerVideo).where(
            InfluencerVideo.video_id == video_id
        )
    )

    if video is None:
        db.add(
            InfluencerVideo(
                influencer_id=influencer_id,
                video_id=video_id,
                **values,
            )
        )
        return True

    if video.influencer_id != influencer_id:
        raise ValueError(
            f"Video {video_id} is already linked to another influencer."
        )

    for field, value in values.items():
        setattr(video, field, value)

    return False


def save_influencer_records(
    db: Session,
    records: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Save discovered influencers and their recent videos.

    Existing influencers and videos are updated.
    Database commit/rollback remains the caller's responsibility.
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list.")

    inserted = 0
    updated = 0
    videos_inserted = 0
    videos_updated = 0
    processed_channel_ids = set()

    for record in records:
        _validate_influencer_record(record)

        channel_id = record["channel_id"].strip()

        if channel_id in processed_channel_ids:
            raise ValueError(
                f"Duplicate channel_id in input: {channel_id}"
            )

        processed_channel_ids.add(channel_id)

        influencer, is_new = _upsert_influencer(db, record)

        if is_new:
            inserted += 1
        else:
            updated += 1

        for video_record in record.get("recent_videos", []):
            was_inserted = _upsert_video(
                db,
                influencer.id,
                video_record,
            )

            if was_inserted:
                videos_inserted += 1
            else:
                videos_updated += 1

    db.flush()

    return {
        "total_processed": len(records),
        "inserted": inserted,
        "updated": updated,
        "videos_inserted": videos_inserted,
        "videos_updated": videos_updated,
    }


def save_enrichment_records(
    db: Session,
    records: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Save or update public enrichment information.

    The influencer must already exist in the database.
    Existing enrichment is updated instead of duplicated.
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list.")

    inserted = 0
    updated = 0
    skipped = 0
    processed_channel_ids = set()

    for record in records:
        if not isinstance(record, dict):
            raise TypeError("Enrichment record must be a dictionary.")

        channel_id = _required_text(record, "channel_id")

        if channel_id in processed_channel_ids:
            raise ValueError(
                f"Duplicate channel_id in enrichment batch: {channel_id}"
            )

        processed_channel_ids.add(channel_id)

        enriched_at = _required_text(record, "enriched_at")

        influencer = db.scalar(
            select(Influencer).where(
                Influencer.channel_id == channel_id
            )
        )

        if influencer is None:
            skipped += 1
            continue

        values = {
            "contact_email": (
                record.get("contact_email") or "Not Found"
            ),
            "contact_emails": _json_list(
                record.get("contact_emails"),
                "contact_emails",
            ),
            "email_status": (
                record.get("email_status") or "not_found"
            ),
            "email_verification_note": _optional_text(
                record.get("email_verification_note")
            ),
            "email_sources": _json_list(
                record.get("email_sources"),
                "email_sources",
            ),
            "public_email_candidates": _json_list(
                record.get("public_email_candidates"),
                "public_email_candidates",
            ),
            "website": record.get("website") or "Not Found",
            "website_urls": _json_list(
                record.get("website_urls"),
                "website_urls",
            ),
            "website_source": _optional_text(
                record.get("website_source")
            ),
            "social_media_links": _json_dict(
                record.get("social_media_links"),
                "social_media_links",
            ),
            "social_link_source": _optional_text(
                record.get("social_link_source")
            ),
            "social_link_ownership_status": _optional_text(
                record.get("social_link_ownership_status")
            ),
            "other_social_platform_links": _json_list(
                record.get("other_social_platform_links"),
                "other_social_platform_links",
            ),
            "content_themes": _json_list(
                record.get("content_themes"),
                "content_themes",
            ),
            "audience_demographics": _json_dict(
                record.get("audience_demographics"),
                "audience_demographics",
            ),
            "enrichment_source": (
                record.get("enrichment_source")
                or "YouTube Data API v3"
            ),
            "enriched_at": enriched_at,
        }

        enrichment = db.scalar(
            select(InfluencerEnrichment).where(
                InfluencerEnrichment.influencer_id == influencer.id
            )
        )

        if enrichment is None:
            db.add(
                InfluencerEnrichment(
                    influencer_id=influencer.id,
                    **values,
                )
            )
            inserted += 1
        else:
            for field, value in values.items():
                setattr(enrichment, field, value)

            updated += 1

    db.flush()

    return {
        "total_processed": len(records),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }


def save_filtering_results(
    db: Session,
    records: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Save or update influencer filtering decisions.

    The newest existing result for an influencer is updated.
    Older historical filtering results are retained.
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list.")

    inserted = 0
    updated = 0
    skipped = 0
    processed_channel_ids = set()

    for record in records:
        if not isinstance(record, dict):
            raise TypeError("Filtering record must be a dictionary.")

        channel_id = _required_text(record, "channel_id")

        if channel_id in processed_channel_ids:
            raise ValueError(
                f"Duplicate channel_id in filtering batch: {channel_id}"
            )

        processed_channel_ids.add(channel_id)

        influencer = db.scalar(
            select(Influencer).where(
                Influencer.channel_id == channel_id
            )
        )

        if influencer is None:
            skipped += 1
            continue

        classification = _required_text(
            record,
            "classification_category",
        )

        filter_status = _required_text(
            record,
            "filter_status",
        ).upper()

        if filter_status not in {"PASS", "FAIL"}:
            raise ValueError(
                f"Invalid filter status for {channel_id}: {filter_status}"
            )

        content_relevant = record.get("content_relevant", False)

        if not isinstance(content_relevant, bool):
            raise ValueError(
                f"content_relevant must be boolean for {channel_id}."
            )

        values = {
            "classification_category": classification,
            "content_relevant": content_relevant,
            "relevance_keywords_found": _json_list(
                record.get("relevance_keywords_found"),
                "relevance_keywords_found",
            ),
            "engagement_rate": _to_optional_float(
                record.get("engagement_rate")
            ),
            "engagement_rate_status": (
                record.get("engagement_rate_status") or "unavailable"
            ),
            "engagement_calculation": _json_dict(
                record.get("engagement_calculation"),
                "engagement_calculation",
            ),
            "filter_results": _json_dict(
                record.get("filter_results"),
                "filter_results",
            ),
            "filter_status": filter_status,
            "filter_reason": _required_text(
                record,
                "filter_reason",
            ),
            "filtered_at": _required_text(
                record,
                "filtered_at",
            ),
        }

        existing = db.scalar(
            select(FilteringResult)
            .where(
                FilteringResult.influencer_id == influencer.id
            )
            .order_by(
                FilteringResult.filtered_at.desc(),
                FilteringResult.id.desc(),
            )
            .limit(1)
        )

        if existing is None:
            db.add(
                FilteringResult(
                    influencer_id=influencer.id,
                    **values,
                )
            )
            inserted += 1
        else:
            for field, value in values.items():
                setattr(existing, field, value)

            updated += 1

    db.flush()

    return {
        "total_processed": len(records),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }


def get_influencer_by_channel_id(
    db: Session,
    channel_id: str,
) -> Influencer | None:
    """Return one influencer using its YouTube channel ID."""
    if not isinstance(channel_id, str) or not channel_id.strip():
        raise ValueError("channel_id must be a non-empty string.")

    return db.scalar(
        select(Influencer).where(
            Influencer.channel_id == channel_id.strip()
        )
    )


def get_all_influencers(
    db: Session,
    limit: int | None = None,
) -> list[Influencer]:
    """Return influencers, newest records first."""
    statement = select(Influencer).order_by(
        Influencer.created_at.desc()
    )

    if limit is not None:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer.")

        statement = statement.limit(limit)

    return list(db.scalars(statement).all())
