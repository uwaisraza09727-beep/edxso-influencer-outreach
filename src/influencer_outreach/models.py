
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.influencer_outreach.database import Base


def _utc_now() -> datetime:
    """Return the current UTC datetime."""

    return datetime.now(timezone.utc)


class Influencer(Base):
    """Store discovered YouTube influencer profiles."""

    __tablename__ = "influencers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    channel_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    channel_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    platform: Mapped[str] = mapped_column(
        String(50),
        default="YouTube",
        nullable=False,
    )

    profile_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    custom_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    channel_country: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    channel_country_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    channel_created_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    subscriber_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    subscriber_count_status: Mapped[str] = mapped_column(
        String(50),
        default="not_returned",
        nullable=False,
    )

    total_views: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    video_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    uploads_playlist_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    matched_keywords: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(100),
        default="YouTube Data API v3",
        nullable=False,
    )

    retrieved_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )

    # Related database records.
    videos: Mapped[list["InfluencerVideo"]] = relationship(
        back_populates="influencer",
        cascade="all, delete-orphan",
    )

    enrichment: Mapped["InfluencerEnrichment | None"] = relationship(
        back_populates="influencer",
        cascade="all, delete-orphan",
        uselist=False,
    )

    filtering_results: Mapped[list["FilteringResult"]] = relationship(
        back_populates="influencer",
        cascade="all, delete-orphan",
    )

    personalized_messages: Mapped[list["PersonalizedMessage"]] = (
        relationship(
            back_populates="influencer",
            cascade="all, delete-orphan",
        )
    )

    outreach_records: Mapped[list["OutreachRecord"]] = relationship(
        back_populates="influencer",
        cascade="all, delete-orphan",
    )


class InfluencerVideo(Base):
    """Store recent public videos belonging to an influencer."""

    __tablename__ = "influencer_videos"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    influencer_id: Mapped[int] = mapped_column(
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    video_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    published_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    video_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    view_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    like_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    comment_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    retrieved_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(100),
        default="YouTube Data API v3",
        nullable=False,
    )

    influencer: Mapped["Influencer"] = relationship(
        back_populates="videos",
    )


class InfluencerEnrichment(Base):
    """Store public contact and enrichment information."""

    __tablename__ = "influencer_enrichments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    influencer_id: Mapped[int] = mapped_column(
        ForeignKey("influencers.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    contact_email: Mapped[str] = mapped_column(
        String(320),
        default="Not Found",
        nullable=False,
    )

    contact_emails: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    email_status: Mapped[str] = mapped_column(
        String(50),
        default="not_found",
        nullable=False,
    )

    email_verification_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    email_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    public_email_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    website: Mapped[str] = mapped_column(
        Text,
        default="Not Found",
        nullable=False,
    )

    website_urls: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    website_source: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    social_media_links: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    social_link_source: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    social_link_ownership_status: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    other_social_platform_links: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    content_themes: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    audience_demographics: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    enrichment_source: Mapped[str] = mapped_column(
        String(150),
        default="YouTube Data API v3",
        nullable=False,
    )

    enriched_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    influencer: Mapped["Influencer"] = relationship(
        back_populates="enrichment",
    )


class FilteringResult(Base):
    """Store PASS/FAIL decisions and individual filtering results."""

    __tablename__ = "filtering_results"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    influencer_id: Mapped[int] = mapped_column(
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    classification_category: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    content_relevant: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    relevance_keywords_found: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    engagement_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    engagement_rate_status: Mapped[str] = mapped_column(
        String(50),
        default="unavailable",
        nullable=False,
    )

    engagement_calculation: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    filter_results: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    filter_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    filter_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    filtered_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    influencer: Mapped["Influencer"] = relationship(
        back_populates="filtering_results",
    )


class PersonalizedMessage(Base):
    """Store Gemini-generated email and Instagram DM messages."""

    __tablename__ = "personalized_messages"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    influencer_id: Mapped[int] = mapped_column(
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email_subject: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    email_pitch: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    email_word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    instagram_dm: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    instagram_dm_word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    generation_status: Mapped[str] = mapped_column(
        String(50),
        default="generated",
        nullable=False,
    )

    generation_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    generation_attempts: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    source_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    generated_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    influencer: Mapped["Influencer"] = relationship(
        back_populates="personalized_messages",
    )

    outreach_records: Mapped[list["OutreachRecord"]] = relationship(
        back_populates="personalized_message",
    )


class OutreachRecord(Base):
    """Store email simulation/sending history and duplicate identifiers."""

    __tablename__ = "outreach_records"

    __table_args__ = (
        UniqueConstraint(
            "influencer_id",
            "normalized_recipient_email",
            name="uq_outreach_influencer_recipient",
        ),
        Index(
            "ix_outreach_status_processed",
            "status",
            "processed_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    influencer_id: Mapped[int] = mapped_column(
        ForeignKey("influencers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    personalized_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("personalized_messages.id"),
        nullable=True,
    )

    recipient_email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )

    normalized_recipient_email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )

    email_subject: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    email_body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    dry_run: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    sent_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    processed_at: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    influencer: Mapped["Influencer"] = relationship(
        back_populates="outreach_records",
    )

    personalized_message: Mapped[
        "PersonalizedMessage | None"
    ] = relationship(
        back_populates="outreach_records",
    )
