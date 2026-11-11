
import os
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()

YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeAPIError(Exception):
    """Raised when a YouTube API request fails."""


class YouTubeClient:
    """Client for interacting with the YouTube Data API v3."""

    def __init__(self) -> None:
        self.api_key = os.getenv("YOUTUBE_API_KEY", "").strip()

        if not self.api_key:
            raise ValueError(
                "YOUTUBE_API_KEY is missing. Check your .env file."
            )

        self.session = requests.Session()

    def _get(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a GET request and handle API errors."""

        url = f"{YOUTUBE_API_BASE_URL}/{endpoint}"

        request_params = {
            **params,
            "key": self.api_key,
        }

        try:
            response = self.session.get(
                url,
                params=request_params,
                timeout=15,
            )

        except requests.RequestException as exc:
            raise YouTubeAPIError(
                "Network error while contacting YouTube API."
            ) from exc

        try:
            data = response.json()

        except ValueError as exc:
            raise YouTubeAPIError(
                "YouTube API returned an invalid response."
            ) from exc

        if response.status_code != 200:
            error = data.get("error", {})

            message = error.get(
                "message",
                "Unknown YouTube API error."
            )

            errors = error.get("errors", [])

            reason = (
                errors[0].get("reason")
                if errors
                else None
            )

            if reason in (
                "quotaExceeded",
                "dailyLimitExceeded",
            ):
                message = (
                    "YouTube API quota exceeded. "
                    "Check your Google Cloud quota."
                )

            elif reason in (
                "rateLimitExceeded",
                "userRateLimitExceeded",
            ):
                message = (
                    "YouTube API rate limit reached. "
                    "Please try again later."
                )

            raise YouTubeAPIError(
                f"YouTube API error ({response.status_code}): "
                f"{message}"
            )

        return data

    def get_channel_by_id(
        self,
        channel_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve public information about one channel."""

        if not channel_id.strip():
            raise ValueError("Channel ID cannot be empty.")

        data = self._get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                "id": channel_id.strip(),
            },
        )

        items = data.get("items", [])

        if not items:
            return None

        return items[0]

    def get_channels_by_ids(
        self,
        channel_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Retrieve information about multiple channels."""

        unique_ids = list(
            dict.fromkeys(
                channel_id.strip()
                for channel_id in channel_ids
                if channel_id and channel_id.strip()
            )
        )

        if not unique_ids:
            raise ValueError(
                "At least one valid channel ID is required."
            )

        if len(unique_ids) > 50:
            raise ValueError(
                "Maximum 50 channel IDs per request."
            )

        data = self._get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(unique_ids),
            },
        )

        return data.get("items", [])

    def search_channels(
        self,
        query: str,
        max_results: int = 5,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """Search YouTube channels using a keyword."""

        if not query.strip():
            raise ValueError(
                "Search query cannot be empty."
            )

        if not 1 <= max_results <= 50:
            raise ValueError(
                "max_results must be between 1 and 50."
            )

        params: dict[str, Any] = {
            "part": "snippet",
            "q": query.strip(),
            "type": "channel",
            "maxResults": max_results,
        }

        if page_token:
            params["pageToken"] = page_token

        return self._get("search", params)

    def search_channels_paginated(
        self,
        query: str,
        total_results: int = 10,
        page_size: int = 5,
        max_pages: int = 2,
    ) -> list[dict[str, Any]]:
        """Search multiple pages with duplicate prevention."""

        if not query.strip():
            raise ValueError(
                "Search query cannot be empty."
            )

        if total_results < 1:
            raise ValueError(
                "total_results must be at least 1."
            )

        if not 1 <= page_size <= 50:
            raise ValueError(
                "page_size must be between 1 and 50."
            )

        if not 1 <= max_pages <= 10:
            raise ValueError(
                "max_pages must be between 1 and 10."
            )

        channels = []
        seen_channel_ids = set()
        page_token = None

        for _ in range(max_pages):

            remaining = total_results - len(channels)

            if remaining <= 0:
                break

            response = self.search_channels(
                query=query,
                max_results=min(page_size, remaining),
                page_token=page_token,
            )

            for item in response.get("items", []):

                channel_id = (
                    item.get("id", {}).get("channelId")
                )

                if not channel_id:
                    continue

                if channel_id in seen_channel_ids:
                    continue

                seen_channel_ids.add(channel_id)
                channels.append(item)

                if len(channels) >= total_results:
                    break

            if len(channels) >= total_results:
                break

            page_token = response.get("nextPageToken")

            if not page_token:
                break

        return channels

    def get_recent_videos(
        self,
        channel_id: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve recent public videos and available statistics."""

        if not channel_id.strip():
            raise ValueError(
                "Channel ID cannot be empty."
            )

        if not 1 <= max_results <= 50:
            raise ValueError(
                "max_results must be between 1 and 50."
            )

        # Step 1: Retrieve channel information.
        channel = self.get_channel_by_id(channel_id)

        if not channel:
            raise YouTubeAPIError(
                "YouTube channel was not found."
            )

        # Step 2: Get the channel's uploads playlist.
        uploads_playlist_id = (
            channel.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )

        if not uploads_playlist_id:
            return []

        # Step 3: Retrieve recent video IDs.
        playlist_data = self._get(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": max_results,
            },
        )

        playlist_items = playlist_data.get("items", [])

        video_ids = [
            item.get("contentDetails", {}).get("videoId")
            for item in playlist_items
            if item.get("contentDetails", {}).get("videoId")
        ]

        if not video_ids:
            return []

        # Step 4: Retrieve available video statistics.
        videos_data = self._get(
            "videos",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(video_ids),
            },
        )

        video_details = {
            video["id"]: video
            for video in videos_data.get("items", [])
            if video.get("id")
        }

        retrieved_at = datetime.now(
            timezone.utc
        ).isoformat()

        results = []

        for item in playlist_items:

            video_id = (
                item.get("contentDetails", {})
                .get("videoId")
            )

            video = video_details.get(video_id)

            # Ignore videos that are no longer publicly available.
            if not video:
                continue

            snippet = video.get("snippet", {})
            statistics = video.get("statistics", {})

            results.append({
                "channel_id": channel_id,
                "video_id": video_id,
                "title": snippet.get(
                    "title",
                    "Not Available"
                ),
                "description": snippet.get(
                    "description",
                    ""
                ),
                "published_at": snippet.get("publishedAt"),
                "video_url": (
                    f"https://www.youtube.com/watch?v={video_id}"
                ),
                "view_count": statistics.get("viewCount"),
                "like_count": statistics.get("likeCount"),
                "comment_count": statistics.get("commentCount"),
                "retrieved_at": retrieved_at,
                "source": "YouTube Data API v3",
            })

        return results
