
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.influencer_outreach.database import SessionLocal
from src.influencer_outreach.integrations.youtube_client import (
    YouTubeAPIError,
)
from src.influencer_outreach.repositories.influencer_repository import (
    save_influencer_records,
)
from src.influencer_outreach.services.discovery import (
    DEFAULT_SEARCH_KEYWORDS,
    discover_influencers,
    save_discovery_records,
)


st.set_page_config(
    page_title="Influencer Discovery | EDXSO",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 Influencer Discovery")

st.markdown(
    """
    Discover genuine technology and AI YouTube influencers
    using the official YouTube Data API v3.
    """
)

st.info(
    """
    **Discovery criteria**

    - Platform: YouTube
    - Niche: Technology & AI
    - Target subscribers: 5,000–100,000 (applied in the
      separate Filtering module)
    - Source: Official YouTube Data API v3

    Discovery itself collects public channel information.
    Filtering eligibility is evaluated separately.
    """
)

# --------------------------------------------------
# DISCOVERY FORM
# --------------------------------------------------

st.subheader("⚙️ Discovery Configuration")

default_keywords = "\n".join(DEFAULT_SEARCH_KEYWORDS)

with st.form("influencer_discovery_form"):

    keywords_text = st.text_area(
        "Search Keywords",
        value=default_keywords,
        height=180,
        help="Enter one technology or AI keyword per line.",
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        target_count = st.number_input(
            "Target Channels",
            min_value=1,
            max_value=50,
            value=50,
            step=1,
        )

    with col2:
        results_per_keyword = st.number_input(
            "Results Per Keyword",
            min_value=1,
            max_value=50,
            value=10,
            step=1,
        )

    with col3:
        recent_video_count = st.selectbox(
            "Recent Videos Per Channel",
            options=[1, 2, 3],
            index=0,
        )

    st.caption(
        "Discovery makes live YouTube API requests. "
        "Recent video retrieval consumes additional API quota. "
        "One video per channel is selected by default."
    )

    submitted = st.form_submit_button(
        "🔎 Discover Influencers",
        type="primary",
        use_container_width=True,
    )


# --------------------------------------------------
# RUN DISCOVERY
# --------------------------------------------------

if submitted:

    keywords = list(
        dict.fromkeys(
            keyword.strip()
            for keyword in keywords_text.splitlines()
            if keyword.strip()
        )
    )

    if not keywords:
        st.error("Please enter at least one search keyword.")

    else:
        st.session_state.pop("discovery_results", None)
        st.session_state.pop("discovery_summary", None)

        database = None

        try:
            with st.spinner(
                "Searching YouTube channels and retrieving public data..."
            ):

                # 1. Discover genuine YouTube channels.
                records = discover_influencers(
                    target_count=int(target_count),
                    results_per_keyword=int(results_per_keyword),
                    recent_video_count=int(recent_video_count),
                    keywords=keywords,
                )

                if not records:
                    st.warning(
                        "No channels were returned by YouTube. "
                        "Try different search keywords."
                    )

                else:

                    # 2. Store records in SQLite.
                    database = SessionLocal()

                    try:
                        database_result = save_influencer_records(
                            database,
                            records,
                        )

                        database.commit()

                    except Exception:
                        database.rollback()
                        raise

                    finally:
                        database.close()
                        database = None

                    # 3. Preserve existing JSON data.
                    raw_path = Path(
                        "data/raw/youtube_influencers.json"
                    )

                    existing_records = []

                    if raw_path.exists():
                        existing_data = json.loads(
                            raw_path.read_text(encoding="utf-8")
                        )

                        existing_records = existing_data.get(
                            "records",
                            [],
                        )

                    # Merge using channel_id as the unique identity.
                    merged_records = {}

                    for record in existing_records + records:
                        channel_id = record.get("channel_id")

                        if channel_id:
                            merged_records[channel_id] = record

                    final_records = list(
                        merged_records.values()
                    )

                    # 4. Save merged discovery history to JSON.
                    json_path = save_discovery_records(
                        final_records,
                        output_path=raw_path,
                    )

                    # 5. Store results in the Streamlit session.
                    st.session_state["discovery_results"] = records

                    st.session_state["discovery_summary"] = {
                        "database": database_result,
                        "json_path": str(json_path),
                        "total_json_records": len(final_records),
                        "keywords": keywords,
                    }

        except YouTubeAPIError as exc:
            st.error(f"YouTube API error: {exc}")

        except ValueError as exc:
            st.error(f"Configuration error: {exc}")

        except Exception as exc:
            st.error(
                "Discovery encountered an unexpected error. "
                "Check the terminal for technical details."
            )
            print(f"Discovery error: {type(exc).__name__}: {exc}")

        finally:
            if database is not None:
                database.close()


# --------------------------------------------------
# DISCOVERY RESULTS
# --------------------------------------------------

records = st.session_state.get("discovery_results")

summary = st.session_state.get("discovery_summary")

if summary:

    st.divider()
    st.subheader("✅ Discovery Completed")

    database_result = summary["database"]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Channels Discovered",
        database_result["total_processed"],
    )

    col2.metric(
        "New Channels",
        database_result["inserted"],
    )

    col3.metric(
        "Existing Channels Updated",
        database_result["updated"],
    )

    col4.metric(
        "Videos Stored",
        (
            database_result["videos_inserted"]
            + database_result["videos_updated"]
        ),
    )

    st.success("Discovery results saved successfully to SQLite.")

    st.write(
        "**JSON output:**",
        summary["json_path"],
    )

    st.write(
        "**Total unique records in JSON:**",
        summary["total_json_records"],
    )

    with st.expander("Search Keywords Used"):
        for keyword in summary["keywords"]:
            st.write(f"- {keyword}")


# --------------------------------------------------
# CHANNEL RESULTS TABLE
# --------------------------------------------------

if records:

    st.divider()
    st.subheader("📋 Discovered Influencer Profiles")

    st.caption(
        "Channel information is retrieved from YouTube. "
        "Subscriber counts may be unavailable or hidden."
    )

    table_data = []

    for record in records:

        table_data.append({
            "Channel Name": record.get(
                "channel_name",
                "Not Available",
            ),
            "Subscribers": record.get("subscriber_count"),
            "Subscriber Status": record.get(
                "subscriber_count_status"
            ),
            "Total Views": record.get("total_views"),
            "Video Count": record.get("video_count"),
            "Recent Videos Retrieved": len(
                record.get("recent_videos", [])
            ),
            "Matched Keywords": ", ".join(
                record.get("matched_keywords", [])
            ),
            "Channel Profile": record.get("profile_url"),
        })

    dataframe = pd.DataFrame(table_data)

    st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Channel Profile": st.column_config.LinkColumn(
                "Channel Profile",
                display_text="Open Channel",
            ),
            "Subscribers": st.column_config.NumberColumn(
                "Subscribers",
                format="%d",
            ),
            "Total Views": st.column_config.NumberColumn(
                "Total Views",
                format="%d",
            ),
        },
    )

    # Detailed video information.
    st.subheader("🎥 Recent Public Videos")

    for record in records:

        videos = record.get("recent_videos", [])

        with st.expander(
            f"{record.get('channel_name', 'Unknown Channel')} "
            f"— {len(videos)} recent videos"
        ):

            if videos:

                for video in videos:

                    st.markdown(
                        f"**[{video.get('title', 'Untitled')}]"
                        f"({video.get('video_url', '')})**"
                    )

                    st.write(
                        "Published:",
                        video.get("published_at") or "Not Available",
                    )

                    st.write(
                        "Views:",
                        video.get("view_count") or "Not Available",
                        "| Likes:",
                        video.get("like_count") or "Not Available",
                        "| Comments:",
                        video.get("comment_count") or "Not Available",
                    )

                    st.divider()

            else:
                st.info(
                    "No public videos were returned for this channel."
                )

            status = record.get(
                "recent_videos_status",
                "unknown",
            )

            st.caption(f"Video retrieval status: {status}")


# --------------------------------------------------
# EMPTY STATE
# --------------------------------------------------

if not records and not summary:

    st.info(
        """
        No new discovery results in this session.

        Configure your keywords and select
        **Discover Influencers** to begin.
        """
    )


st.divider()

st.caption(
    "EDXSO Influencer Outreach | "
    "Data source: YouTube Data API v3"
)
