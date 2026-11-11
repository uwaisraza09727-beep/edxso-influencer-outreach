
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


load_dotenv()


CLASSIFICATION_KEYWORDS = {
    "Generative AI & LLM": [
        "generative ai",
        "genai",
        "large language model",
        "large language models",
        "llm",
        "llms",
        "prompt engineering",
        "context window",
        "rag",
        "retrieval augmented generation",
        "agentic ai",
        "ai agents",
    ],
    "Machine Learning & Deep Learning": [
        "machine learning",
        "deep learning",
        "neural network",
        "neural networks",
        "computer vision",
        "natural language processing",
        "nlp",
        "tensorflow",
        "pytorch",
        "scikit-learn",
    ],
    "AI Tools & Automation": [
        "ai tools",
        "ai automation",
        "automation with ai",
        "ai workflow",
        "ai workflows",
        "ai assistants",
        "artificial intelligence",
        "ai-powered",
    ],
    "Python & Data Science": [
        "python",
        "data science",
        "data analytics",
        "pandas",
        "numpy",
        "jupyter",
        "data analysis",
    ],
    "Software & Technology Education": [
        "programming",
        "software development",
        "coding",
        "web development",
        "backend development",
        "api development",
        "cloud computing",
        "developer tools",
        "technology tutorials",
    ],
}


def _read_int_setting(name: str, default: int) -> int:
    """Read an integer configuration value."""

    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid integer configuration: {name}"
        ) from exc


def _read_float_setting(name: str, default: float) -> float:
    """Read a numeric configuration value."""

    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid numeric configuration: {name}"
        ) from exc


def _to_optional_int(value: Any) -> int | None:
    """Convert a value to a non-negative integer."""

    if value is None:
        return None

    try:
        result = int(value)
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


def calculate_engagement_rate(
    videos: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Calculate pooled recent-video engagement.

    Formula:
    (Total likes + Total comments) / Total views * 100
    """

    total_views = 0
    total_likes = 0
    total_comments = 0
    videos_used = 0

    for video in videos:

        views = _to_optional_int(video.get("view_count"))
        likes = _to_optional_int(video.get("like_count"))
        comments = _to_optional_int(video.get("comment_count"))

        if (
            views is None
            or likes is None
            or comments is None
            or views <= 0
        ):
            continue

        total_views += views
        total_likes += likes
        total_comments += comments
        videos_used += 1

    if total_views == 0:
        return {
            "engagement_rate": None,
            "total_views": 0,
            "total_likes": 0,
            "total_comments": 0,
            "videos_used": 0,
            "status": "unavailable",
            "formula": (
                "(Total likes + Total comments) "
                "/ Total views * 100"
            ),
        }

    engagement_rate = (
        (total_likes + total_comments) / total_views
    ) * 100

    return {
        "engagement_rate": round(engagement_rate, 2),
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "videos_used": videos_used,
        "status": "calculated",
        "formula": (
            "(Total likes + Total comments) "
            "/ Total views * 100"
        ),
    }


def _find_keyword_matches(
    text: str,
    keywords: list[str],
) -> list[str]:
    """Find actual keyword matches in channel content."""

    matches = []

    for keyword in keywords:

        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(keyword.lower())
            + r"(?![a-z0-9])"
        )

        if re.search(pattern, text):
            matches.append(keyword)

    return matches


def classify_influencer(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Classify a channel using available public content."""

    text_parts = [
        record.get("channel_name") or "",
        record.get("description") or "",
    ]

    for video in record.get("recent_videos") or []:
        text_parts.append(video.get("title") or "")
        text_parts.append(video.get("description") or "")

    content_text = " ".join(text_parts).lower()

    category_matches = {}

    for category, keywords in CLASSIFICATION_KEYWORDS.items():

        matches = _find_keyword_matches(
            content_text,
            keywords,
        )

        if matches:
            category_matches[category] = matches

    if not category_matches:
        return {
            "classification_category": (
                "Not Classified - Insufficient Content Evidence"
            ),
            "content_relevant": False,
            "relevance_keywords_found": [],
            "matched_categories": [],
        }

    category_scores = Counter({
        category: len(matches)
        for category, matches in category_matches.items()
    })

    best_category = category_scores.most_common(1)[0][0]

    all_matches = [
        keyword
        for matches in category_matches.values()
        for keyword in matches
    ]

    return {
        "classification_category": best_category,
        "content_relevant": True,
        "relevance_keywords_found": all_matches,
        "matched_categories": list(category_matches.keys()),
    }


def evaluate_influencer(
    record: dict[str, Any],
    min_followers: int,
    max_followers: int,
    min_engagement_rate: float,
) -> dict[str, Any]:
    """Evaluate one influencer against the required criteria."""

    result = dict(record)

    subscriber_count = _to_optional_int(
        record.get("subscriber_count")
    )

    subscriber_status = record.get(
        "subscriber_count_status",
        "available",
    )

    if subscriber_status != "available":
        subscriber_count = None

    # Criterion 1: Follower range.
    follower_pass = (
        subscriber_count is not None
        and min_followers <= subscriber_count <= max_followers
    )

    if subscriber_count is None:
        follower_reason = (
            "Subscriber count is unavailable or hidden."
        )
    elif follower_pass:
        follower_reason = (
            "Subscriber count is within the configured range."
        )
    else:
        follower_reason = (
            f"Subscriber count {subscriber_count} is outside "
            f"the range {min_followers}-{max_followers}."
        )

    # Criterion 2: Content relevance.
    classification = classify_influencer(record)

    content_pass = classification["content_relevant"]

    if content_pass:
        content_reason = (
            "Relevant Technology or AI content keywords "
            "were found in the available channel information "
            "or recent videos."
        )
    else:
        content_reason = (
            "No matching Technology or AI content keywords "
            "were found in the available information."
        )

    # Criterion 3: Engagement rate.
    engagement = calculate_engagement_rate(
        record.get("recent_videos") or []
    )

    engagement_rate = engagement["engagement_rate"]

    engagement_pass = (
        engagement_rate is not None
        and engagement_rate >= min_engagement_rate
    )

    if engagement_rate is None:
        engagement_reason = (
            "Engagement rate could not be calculated "
            "because sufficient video statistics were unavailable."
        )
    elif engagement_pass:
        engagement_reason = (
            "Calculated recent-video engagement meets "
            "the configured minimum."
        )
    else:
        engagement_reason = (
            f"Calculated engagement rate {engagement_rate}% "
            f"is below the required {min_engagement_rate}%."
        )

    # Criterion 4: Platform.
    platform = record.get("platform")
    platform_pass = platform == "YouTube"

    platform_reason = (
        "Platform matches YouTube."
        if platform_pass
        else "Platform does not match YouTube."
    )

    # Geography is informational, not a mandatory rejection rule.
    geography = {
        "available": bool(record.get("channel_country")),
        "channel_country": record.get("channel_country"),
        "note": "Channel country is not audience geography.",
    }

    filter_results = {
        "follower_range": {
            "passed": follower_pass,
            "actual": subscriber_count,
            "minimum": min_followers,
            "maximum": max_followers,
            "reason": follower_reason,
        },
        "content_relevance": {
            "passed": content_pass,
            "reason": content_reason,
            "keywords_found": (
                classification["relevance_keywords_found"]
            ),
        },
        "engagement_rate": {
            "passed": engagement_pass,
            "actual": engagement_rate,
            "minimum": min_engagement_rate,
            "reason": engagement_reason,
            "calculation": engagement,
        },
        "platform": {
            "passed": platform_pass,
            "actual": platform,
            "expected": "YouTube",
            "reason": platform_reason,
        },
        "geography": geography,
    }

    mandatory_results = [
        follower_pass,
        content_pass,
        engagement_pass,
        platform_pass,
    ]

    overall_pass = all(mandatory_results)

    failure_reasons = [
        details["reason"]
        for name, details in filter_results.items()
        if name != "geography" and not details["passed"]
    ]

    result.update({
        "classification_category": (
            classification["classification_category"]
        ),
        "content_relevant": content_pass,
        "relevance_keywords_found": (
            classification["relevance_keywords_found"]
        ),
        "engagement_rate": engagement_rate,
        "engagement_rate_status": engagement["status"],
        "engagement_calculation": engagement,
        "filter_results": filter_results,
        "filter_status": (
            "PASS" if overall_pass else "FAIL"
        ),
        "filter_reason": (
            "Passed all mandatory filtering criteria."
            if overall_pass
            else " ".join(failure_reasons)
        ),
        "filtered_at": datetime.now(
            timezone.utc
        ).isoformat(),
    })

    return result


def filter_influencers(
    records: list[dict[str, Any]],
    min_followers: int | None = None,
    max_followers: int | None = None,
    min_engagement_rate: float | None = None,
) -> list[dict[str, Any]]:
    """Filter and classify discovered influencer records."""

    if not records:
        return []

    if min_followers is None:
        min_followers = _read_int_setting(
            "MIN_FOLLOWERS",
            5000,
        )

    if max_followers is None:
        max_followers = _read_int_setting(
            "MAX_FOLLOWERS",
            100000,
        )

    if min_engagement_rate is None:
        min_engagement_rate = _read_float_setting(
            "MIN_ENGAGEMENT_RATE",
            2.0,
        )

    if min_followers < 0:
        raise ValueError(
            "Minimum followers cannot be negative."
        )

    if max_followers < min_followers:
        raise ValueError(
            "Maximum followers cannot be less than minimum followers."
        )

    if min_engagement_rate < 0:
        raise ValueError(
            "Minimum engagement rate cannot be negative."
        )

    return [
        evaluate_influencer(
            record=record,
            min_followers=min_followers,
            max_followers=max_followers,
            min_engagement_rate=min_engagement_rate,
        )
        for record in records
    ]


def save_filtering_results(
    records: list[dict[str, Any]],
    output_path: str | Path | None = None,
) -> Path:
    """Save all filtering and classification results as JSON."""

    if not records:
        raise ValueError(
            "No filtering results available to save."
        )

    channel_ids = [
        record.get("channel_id")
        for record in records
    ]

    if None in channel_ids:
        raise ValueError(
            "A filtering result is missing its channel ID."
        )

    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError(
            "Duplicate channel IDs found in filtering results."
        )

    for record in records:

        if record.get("filter_status") not in ("PASS", "FAIL"):
            raise ValueError(
                "A record has an invalid filtering status."
            )

        if not record.get("filter_results"):
            raise ValueError(
                "Individual filtering results are missing."
            )

        if not record.get("classification_category"):
            raise ValueError(
                "A classification category is missing."
            )

    if output_path is None:

        project_root = Path(__file__).resolve().parents[3]

        destination = (
            project_root
            / "data"
            / "processed"
            / "filtered_influencers.json"
        )

    else:
        destination = Path(output_path)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pass_count = sum(
        record["filter_status"] == "PASS"
        for record in records
    )

    fail_count = sum(
        record["filter_status"] == "FAIL"
        for record in records
    )

    payload = {
        "metadata": {
            "source": "YouTube Data API v3",
            "saved_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "total_records": len(records),
            "unique_channel_count": len(set(channel_ids)),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "filtering_criteria": {
                "minimum_followers": _read_int_setting(
                    "MIN_FOLLOWERS",
                    5000,
                ),
                "maximum_followers": _read_int_setting(
                    "MAX_FOLLOWERS",
                    100000,
                ),
                "minimum_engagement_rate": _read_float_setting(
                    "MIN_ENGAGEMENT_RATE",
                    2.0,
                ),
                "required_platform": "YouTube",
                "required_niche": "Technology & AI",
            },
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
