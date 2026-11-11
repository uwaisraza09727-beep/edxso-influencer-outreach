
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.influencer_outreach.integrations.youtube_client import (
    YouTubeAPIError,
    YouTubeClient,
)


DEFAULT_SEARCH_KEYWORDS = [
    "artificial intelligence",
    "generative AI",
    "machine learning",
    "AI tools",
    "Python AI tutorials",
    "large language models",
    "data science tutorials",
    "deep learning",
    "AI automation",
    "technology tutorials",
]


def _to_optional_int(value: Any) -> int | None:
    """Convert an API value to integer without inventing missing data."""

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def discover_influencers(
    target_count: int = 50,
    results_per_keyword: int = 10,
    recent_video_count: int = 3,
    keywords: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Discover genuine YouTube channels using the official API."""

    if target_count < 1:
        raise ValueError("target_count must be at least 1.")

    if not 1 <= results_per_keyword <= 50:
        raise ValueError(
            "results_per_keyword must be between 1 and 50."
        )

    if not 1 <= recent_video_count <= 50:
        raise ValueError(
            "recent_video_count must be between 1 and 50."
        )

    search_keywords = keywords or DEFAULT_SEARCH_KEYWORDS

    if not search_keywords:
        raise ValueError("At least one search keyword is required.")

    client = YouTubeClient()

    candidates: dict[str, dict[str, Any]] = {}

    # Step 1: Search channels using niche keywords.
    for keyword in search_keywords:

        if len(candidates) >= target_count:
            break

        keyword = keyword.strip()

        if not keyword:
            continue

        remaining = target_count - len(candidates)

        try:
            search_results = client.search_channels_paginated(
                query=keyword,
                total_results=min(results_per_keyword, remaining),
                page_size=min(results_per_keyword, 50),
                max_pages=1,
            )

        except YouTubeAPIError as exc:
            raise YouTubeAPIError(
                f"Discovery failed for keyword '{keyword}': {exc}"
            ) from exc

        for item in search_results:

            channel_id = (
                item.get("id", {}).get("channelId")
            )

            if not channel_id:
                continue

            if channel_id not in candidates:

                snippet = item.get("snippet", {})

                candidates[channel_id] = {
                    "channel_id": channel_id,
                    "search_result_title": snippet.get(
                        "title",
                        "Not Available",
                    ),
                    "matched_keywords": [keyword],
                }

            elif keyword not in candidates[channel_id]["matched_keywords"]:

                candidates[channel_id]["matched_keywords"].append(
                    keyword
                )

            if len(candidates) >= target_count:
                break

    if not candidates:
        return []

    # Step 2: Fetch channel details in batches.
    channel_ids = list(candidates.keys())

    channel_details = []

    for start in range(0, len(channel_ids), 50):

        batch_ids = channel_ids[start:start + 50]

        batch_details = client.get_channels_by_ids(batch_ids)

        channel_details.extend(batch_details)

    retrieved_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    # Step 3: Build channel records.
    for channel in channel_details:

        channel_id = channel.get("id")

        snippet = channel.get("snippet") or {}
        statistics = channel.get("statistics") or {}
        content_details = channel.get("contentDetails") or {}

        subscriber_value = statistics.get("subscriberCount")

        hidden_subscribers = statistics.get(
            "hiddenSubscriberCount",
            False,
        )

        if hidden_subscribers:
            subscriber_status = "hidden"
        elif subscriber_value is None:
            subscriber_status = "not_returned"
        else:
            subscriber_status = "available"

        record = {
            "channel_id": channel_id,
            "channel_name": snippet.get(
                "title",
                "Not Available",
            ),
            "platform": "YouTube",
            "profile_url": (
                f"https://www.youtube.com/channel/{channel_id}"
            ),
            "custom_url": snippet.get("customUrl"),
            "description": snippet.get("description", ""),
            "channel_country": snippet.get("country"),
            "channel_country_note": (
                "Channel country, not audience geography."
            ),
            "channel_created_at": snippet.get("publishedAt"),
            "subscriber_count": _to_optional_int(
                subscriber_value
            ),
            "subscriber_count_status": subscriber_status,
            "total_views": _to_optional_int(
                statistics.get("viewCount")
            ),
            "video_count": _to_optional_int(
                statistics.get("videoCount")
            ),
            "uploads_playlist_id": (
                content_details
                .get("relatedPlaylists", {})
                .get("uploads")
            ),
            "matched_keywords": candidates.get(
                channel_id,
                {},
            ).get("matched_keywords", []),
            "source": "YouTube Data API v3",
            "retrieved_at": retrieved_at,
            "recent_videos": [],
            "recent_videos_status": "not_fetched",
        }

        records.append(record)

    # Step 4: Retrieve recent public videos.
    for record in records:

        channel_id = record["channel_id"]

        try:
            videos = client.get_recent_videos(
                channel_id=channel_id,
                max_results=recent_video_count,
            )

            record["recent_videos"] = videos

            record["recent_videos_status"] = (
                "retrieved"
                if videos
                else "no_public_videos_returned"
            )

        except YouTubeAPIError as exc:

            error_message = str(exc).lower()

            if (
                "quota exceeded" in error_message
                or "rate limit" in error_message
            ):
                raise

            record["recent_videos_status"] = "unavailable"
            record["recent_videos_error"] = str(exc)

    return records


def save_discovery_records(
    records: list[dict[str, Any]],
    output_path: str | Path | None = None,
) -> Path:
    """Save raw discovery records and metadata to a JSON file."""

    if not records:
        raise ValueError("No discovery records available to save.")

    channel_ids = [
        record.get("channel_id")
        for record in records
    ]

    if None in channel_ids:
        raise ValueError("A record is missing its channel ID.")

    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError("Duplicate channel IDs found.")

    for record in records:

        if not record.get("profile_url"):
            raise ValueError(
                "A record is missing its profile source URL."
            )

        if not record.get("retrieved_at"):
            raise ValueError(
                "A record is missing its retrieval timestamp."
            )

    if output_path is None:

        project_root = Path(__file__).resolve().parents[3]

        destination = (
            project_root
            / "data"
            / "raw"
            / "youtube_influencers.json"
        )

    else:
        destination = Path(output_path)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "metadata": {
            "source": "YouTube Data API v3",
            "saved_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "record_count": len(records),
            "unique_channel_count": len(set(channel_ids)),
        },
        "records": records,
    }

    with destination.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            indent=4,
            ensure_ascii=False,
        )

    return destination
