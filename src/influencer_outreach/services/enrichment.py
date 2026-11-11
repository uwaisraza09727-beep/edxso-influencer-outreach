
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.influencer_outreach.services.filtering import (
    CLASSIFICATION_KEYWORDS,
)


EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

URL_PATTERN = re.compile(
    r"""(?:https?://|www\.)[^\s<>"']+""",
    re.IGNORECASE,
)

SOCIAL_DOMAINS = {
    "instagram.com": "Instagram",
    "x.com": "X",
    "twitter.com": "X",
    "linkedin.com": "LinkedIn",
    "tiktok.com": "TikTok",
    "facebook.com": "Facebook",
    "github.com": "GitHub",
    "threads.net": "Threads",
    "reddit.com": "Reddit",
    "t.me": "Telegram",
}

NON_WEBSITE_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "creativecommons.org",
    "google.com",
    "g.co",
    "forms.gle",
}

TRAILING_URL_CHARACTERS = ".,;:!?)]}"

RESERVED_SOCIAL_PATHS = {
    "instagram": {
        "p", "reel", "reels", "stories", "explore",
        "accounts", "direct", "share",
    },
    "x": {
        "home", "search", "explore", "settings",
        "compose", "i", "intent",
    },
}


def extract_emails(text: str) -> list[str]:
    """Extract email addresses explicitly present in public text."""

    if not text:
        return []

    return list(dict.fromkeys(EMAIL_PATTERN.findall(text)))


def extract_urls(text: str) -> list[str]:
    """Extract publicly displayed HTTP and HTTPS URLs."""

    if not text:
        return []

    matches = URL_PATTERN.findall(text)
    urls = []

    for value in matches:

        value = value.rstrip(TRAILING_URL_CHARACTERS)

        if value.lower().startswith("www."):
            value = "https://" + value

        parsed = urlparse(value)

        if parsed.scheme not in ("http", "https"):
            continue

        if not parsed.hostname:
            continue

        urls.append(value)

    return list(dict.fromkeys(urls))


def _get_domain(url: str) -> str:
    """Return a normalized URL domain."""

    domain = (urlparse(url).hostname or "").lower()

    return domain.removeprefix("www.")


def _get_path_parts(url: str) -> list[str]:
    """Return non-empty URL path components."""

    return [
        part
        for part in urlparse(url).path.split("/")
        if part
    ]


def _is_non_website_domain(domain: str) -> bool:
    """Identify generic platform and reference domains."""

    return any(
        domain == blocked
        or domain.endswith("." + blocked)
        for blocked in NON_WEBSITE_DOMAINS
    )


def _is_social_profile_url(url: str) -> bool:
    """Check whether a URL has a recognizable social profile path."""

    domain = _get_domain(url)
    parts = _get_path_parts(url)

    if not parts:
        return False

    if domain == "instagram.com":
        return (
            len(parts) == 1
            and parts[0].lower()
            not in RESERVED_SOCIAL_PATHS["instagram"]
        )

    if domain in ("x.com", "twitter.com"):
        return (
            len(parts) == 1
            and parts[0].lower()
            not in RESERVED_SOCIAL_PATHS["x"]
        )

    if domain == "linkedin.com":
        return (
            len(parts) == 2
            and parts[0].lower() in ("in", "company", "school")
        )

    if domain == "github.com":
        # GitHub profile: github.com/username
        # Repository: github.com/username/repository
        return len(parts) == 1

    if domain == "tiktok.com":
        return (
            len(parts) == 1
            and parts[0].startswith("@")
        )

    if domain == "facebook.com":
        return (
            len(parts) == 1
            and parts[0].lower() not in ("watch", "groups", "events")
        )

    if domain == "threads.net":
        return (
            len(parts) == 1
            and parts[0].startswith("@")
        )

    if domain == "reddit.com":
        return (
            len(parts) == 2
            and parts[0].lower() == "user"
        )

    if domain == "t.me":
        return len(parts) == 1

    return False


def identify_social_links(
    urls: list[str],
) -> tuple[dict[str, list[str]], list[str]]:
    """
    Identify recognizable social profile URLs.

    Repository URLs and ordinary platform content links
    are not classified as personal social profiles.
    """

    social_links: dict[str, list[str]] = {}
    other_links = []

    for url in urls:

        domain = _get_domain(url)

        platform = SOCIAL_DOMAINS.get(domain)

        if (
            platform
            and _is_social_profile_url(url)
        ):

            social_links.setdefault(
                platform,
                [],
            ).append(url)

        elif platform:
            # Examples: GitHub repositories or ordinary
            # social platform posts, not profile links.
            other_links.append(url)

    social_links = {
        platform: list(dict.fromkeys(links))
        for platform, links in social_links.items()
    }

    return social_links, list(dict.fromkeys(other_links))


def _identify_websites(
    urls: list[str],
) -> list[str]:
    """Identify external website URLs, excluding social platforms."""

    websites = []

    social_domains = set(SOCIAL_DOMAINS.keys())

    for url in urls:

        domain = _get_domain(url)

        is_social_domain = any(
            domain == social_domain
            or domain.endswith("." + social_domain)
            for social_domain in social_domains
        )

        if is_social_domain:
            continue

        if _is_non_website_domain(domain):
            continue

        websites.append(url)

    return list(dict.fromkeys(websites))


def extract_content_themes(
    record: dict[str, Any],
) -> list[str]:
    """Identify themes from actual channel and video text."""

    text_parts = [
        record.get("channel_name") or "",
        record.get("description") or "",
    ]

    for video in record.get("recent_videos") or []:

        text_parts.append(video.get("title") or "")
        text_parts.append(video.get("description") or "")

    content_text = " ".join(text_parts).lower()

    themes = []

    for category, keywords in CLASSIFICATION_KEYWORDS.items():

        for keyword in keywords:

            pattern = (
                r"(?<![a-z0-9])"
                + re.escape(keyword.lower())
                + r"(?![a-z0-9])"
            )

            if re.search(pattern, content_text):
                themes.append(keyword)

    return list(dict.fromkeys(themes))


def enrich_influencer(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Enrich an influencer using collected public information."""

    enriched = dict(record)

    channel_description = record.get("description") or ""

    recent_videos = record.get("recent_videos") or []

    # Only channel-description emails are used as contact emails.
    # Emails in individual video descriptions are preserved
    # separately because they may belong to another person.

    email_sources = []

    for email in extract_emails(channel_description):

        email_sources.append({
            "email": email,
            "source_url": record.get(
                "profile_url",
                "Not Available",
            ),
            "source_type": "Public channel description",
        })

    public_email_candidates = []

    for video in recent_videos:

        for email in extract_emails(
            video.get("description") or ""
        ):

            public_email_candidates.append({
                "email": email,
                "source_url": video.get(
                    "video_url",
                    "Not Available",
                ),
                "source_type": "Public video description",
                "ownership_status": "Not independently verified",
            })

    unique_emails = {}

    for item in email_sources:

        unique_emails.setdefault(
            item["email"].lower(),
            item,
        )

    contact_emails = list(unique_emails.values())

    if contact_emails:
        contact_email = contact_emails[0]["email"]
        email_status = "publicly_listed"
    else:
        contact_email = "Not Found"
        email_status = "not_found"

    # Social and website links are sourced only from
    # the channel's own public description.
    # We still do not claim independent ownership verification.

    channel_urls = extract_urls(channel_description)

    social_links, other_social_links = identify_social_links(
        channel_urls
    )

    website_urls = _identify_websites(channel_urls)

    content_themes = extract_content_themes(record)

    audience_information = {
        "age": "Not Available",
        "gender": "Not Available",
        "geography": "Not Available",
        "source": (
            "YouTube Data API v3 does not provide "
            "these channel audience analytics."
        ),
    }

    enriched.update({
        "influencer_name": record.get(
            "channel_name",
            "Not Available",
        ),
        "contact_email": contact_email,
        "contact_emails": [
            item["email"]
            for item in contact_emails
        ],
        "email_status": email_status,
        "email_verification_note": (
            "Publicly listed in the channel description; "
            "mailbox deliverability is not verified."
        ),
        "email_sources": contact_emails,
        "public_email_candidates": public_email_candidates,
        "website": (
            website_urls[0]
            if website_urls
            else "Not Found"
        ),
        "website_urls": website_urls,
        "website_source": (
            "Public channel description"
            if website_urls
            else "Not Found"
        ),
        "social_media_links": social_links,
        "social_link_source": (
            "Public channel description"
            if social_links
            else "Not Found"
        ),
        "social_link_ownership_status": (
            "Listed in channel description; "
            "ownership not independently verified."
        ),
        "other_social_platform_links": other_social_links,
        "content_themes": content_themes,
        "audience_demographics": audience_information,
        "enrichment_source": "YouTube Data API v3",
        "enriched_at": datetime.now(
            timezone.utc
        ).isoformat(),
    })

    return enriched


def enrich_influencers(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich multiple influencer records."""

    if not records:
        return []

    enriched_records = []

    for record in records:

        if not record.get("channel_id"):
            raise ValueError(
                "Cannot enrich a record without a channel ID."
            )

        enriched_records.append(
            enrich_influencer(record)
        )

    return enriched_records


def save_enriched_records(
    records: list[dict[str, Any]],
    output_path: str | Path | None = None,
) -> Path:
    """Save enriched influencer records as JSON."""

    if not records:
        raise ValueError(
            "No enriched records available to save."
        )

    channel_ids = [
        record.get("channel_id")
        for record in records
    ]

    if None in channel_ids:
        raise ValueError(
            "An enriched record is missing its channel ID."
        )

    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError(
            "Duplicate channel IDs found."
        )

    for record in records:

        if not record.get("contact_email"):
            raise ValueError(
                "Mandatory contact email field is missing."
            )

    if output_path is None:

        project_root = Path(__file__).resolve().parents[3]

        destination = (
            project_root
            / "data"
            / "processed"
            / "enriched_influencers.json"
        )

    else:
        destination = Path(output_path)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "metadata": {
            "source": "Public YouTube Data API v3 information",
            "saved_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "total_records": len(records),
            "unique_channel_count": len(set(channel_ids)),
            "emails_found": sum(
                record["email_status"] == "publicly_listed"
                for record in records
            ),
            "emails_not_found": sum(
                record["email_status"] == "not_found"
                for record in records
            ),
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
