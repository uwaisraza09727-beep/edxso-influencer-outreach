
import os
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.influencer_outreach.database import SessionLocal
from src.influencer_outreach.services.filtering import (
    filter_influencers,
    save_filtering_results as save_filtering_json,
)
from src.influencer_outreach.repositories.influencer_repository import (
    save_filtering_results as save_filtering_database,
)


st.set_page_config(
    page_title="Influencer Filtering | EDXSO",
    page_icon="🎯",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "youtube_influencers.json"
)


def get_filtering_thresholds():
    """Read filtering criteria from the environment."""
    minimum = int(os.getenv("MIN_FOLLOWERS", "5000"))
    maximum = int(os.getenv("MAX_FOLLOWERS", "100000"))
    engagement = float(
        os.getenv("MIN_ENGAGEMENT_RATE", "2.0")
    )

    if minimum < 0 or maximum < minimum or engagement < 0:
        raise ValueError("Invalid filtering configuration.")

    return minimum, maximum, engagement


def load_raw_records():
    """Load discovered channel records from the raw JSON file."""
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            "Discovery data not found. Run Influencer Discovery first."
        )

    data = json.loads(
        RAW_FILE.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError("Invalid discovery JSON structure.")

    records = data.get("records", [])

    if not isinstance(records, list):
        raise ValueError("Discovery records must be a list.")

    return records


st.title("🎯 Influencer Filtering & Classification")

st.markdown(
    """
    Evaluate discovered YouTube channels against the
    Technology & AI influencer qualification criteria.
    """
)

# --------------------------------------------------
# FILTER CONFIGURATION
# --------------------------------------------------

try:
    min_followers, max_followers, min_engagement = (
        get_filtering_thresholds()
    )

    raw_records = load_raw_records()

except Exception as exc:
    st.error(f"Unable to load filtering configuration or data: {exc}")
    st.stop()


st.subheader("⚙️ Filtering Criteria")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Discovered Channels", len(raw_records))
col2.metric("Minimum Subscribers", f"{min_followers:,}")
col3.metric("Maximum Subscribers", f"{max_followers:,}")
col4.metric("Minimum Engagement", f"{min_engagement}%")

st.info(
    """
    **Mandatory criteria**

    1. Subscriber count between configured minimum and maximum.
    2. Relevant Technology or AI content.
    3. Calculated recent-video engagement meets the minimum.
    4. Platform must be YouTube.

    Geography is informational only. Missing subscriber or
    engagement information is not treated as a passing result.
    """
)

st.caption(
    "Filtering uses the local discovery JSON file. "
    "No new YouTube API requests are made."
)

# --------------------------------------------------
# RUN FILTERING
# --------------------------------------------------

st.subheader("🚀 Evaluate Influencers")

if st.button(
    "🎯 Evaluate All Influencers",
    type="primary",
    use_container_width=True,
):

    if not raw_records:
        st.warning("No discovered influencer records are available.")

    else:
        try:
            with st.spinner(
                "Evaluating subscriber counts, content relevance "
                "and engagement rates..."
            ):

                # 1. Evaluate all discovered records.
                results = filter_influencers(
                    records=raw_records,
                    min_followers=min_followers,
                    max_followers=max_followers,
                    min_engagement_rate=min_engagement,
                )

                pass_count = sum(
                    item["filter_status"] == "PASS"
                    for item in results
                )

                fail_count = sum(
                    item["filter_status"] == "FAIL"
                    for item in results
                )

                # 2. Save complete filtering snapshot to JSON.
                json_path = save_filtering_json(results)

                # 3. Save or update database records.
                db = SessionLocal()

                try:
                    database_result = save_filtering_database(
                        db,
                        results,
                    )
                    db.commit()

                except Exception:
                    db.rollback()
                    raise

                finally:
                    db.close()

                # 4. Store results for page display.
                st.session_state["filtering_results"] = results

                st.session_state["filtering_summary"] = {
                    "total": len(results),
                    "passed": pass_count,
                    "failed": fail_count,
                    "json_path": str(json_path),
                    "database": database_result,
                }

            st.success(
                "All influencer filtering results saved successfully."
            )

        except Exception as exc:
            st.error(
                "Filtering could not be completed. "
                "Check the technical details below."
            )
            st.exception(exc)


# --------------------------------------------------
# RESULTS SUMMARY
# --------------------------------------------------

results = st.session_state.get("filtering_results")
summary = st.session_state.get("filtering_summary")

if summary:

    st.divider()
    st.subheader("✅ Filtering Summary")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Evaluated", summary["total"])
    col2.metric("Qualified (PASS)", summary["passed"])
    col3.metric("Not Qualified (FAIL)", summary["failed"])

    pass_rate = (
        summary["passed"] / summary["total"] * 100
        if summary["total"]
        else 0
    )

    col4.metric("Qualification Rate", f"{pass_rate:.1f}%")

    database_result = summary["database"]

    st.write("**SQLite database results**")

    db_col1, db_col2, db_col3 = st.columns(3)

    db_col1.metric(
        "New Results",
        database_result["inserted"],
    )

    db_col2.metric(
        "Updated Results",
        database_result["updated"],
    )

    db_col3.metric(
        "Skipped Records",
        database_result["skipped"],
    )

    st.write("**JSON output:**", summary["json_path"])

    # --------------------------------------------------
    # CLASSIFICATION SUMMARY
    # --------------------------------------------------

    st.divider()
    st.subheader("📊 Influencer Classification")

    category_counts = (
        pd.DataFrame(results)
        .groupby("classification_category")
        .size()
        .reset_index(name="Influencers")
        .sort_values("Influencers", ascending=False)
    )

    st.bar_chart(
        category_counts.set_index("classification_category"),
        y="Influencers",
    )

    # --------------------------------------------------
    # PASS / FAIL FILTER
    # --------------------------------------------------

    st.divider()
    st.subheader("📋 Filtering Results")

    selected_status = st.selectbox(
        "Filter by qualification status",
        ["All", "PASS", "FAIL"],
    )

    displayed_results = results

    if selected_status != "All":
        displayed_results = [
            item
            for item in results
            if item["filter_status"] == selected_status
        ]

    table_data = []

    for item in displayed_results:

        table_data.append({
            "Channel Name": item.get("channel_name"),
            "Subscribers": item.get("subscriber_count"),
            "Category": item.get("classification_category"),
            "Engagement Rate (%)": item.get("engagement_rate"),
            "Engagement Status": item.get(
                "engagement_rate_status"
            ),
            "Filter Status": item.get("filter_status"),
            "Channel Profile": item.get("profile_url"),
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
            "Engagement Rate (%)": st.column_config.NumberColumn(
                "Engagement Rate (%)",
                format="%.2f%%",
            ),
        },
    )

    st.caption(
        f"Showing {len(displayed_results)} "
        f"of {len(results)} evaluated channels."
    )

    # --------------------------------------------------
    # INDIVIDUAL FILTER DETAILS
    # --------------------------------------------------

    st.divider()
    st.subheader("🔍 Individual Evaluation Details")

    for item in displayed_results:

        channel_name = item.get(
            "channel_name",
            "Unknown Channel",
        )

        status = item.get("filter_status", "UNKNOWN")

        with st.expander(
            f"{'✅' if status == 'PASS' else '❌'} "
            f"{channel_name} — {status}"
        ):

            st.write(
                "**Channel Profile:**",
                item.get("profile_url", "Not Available"),
            )

            st.write(
                "**Classification:**",
                item.get("classification_category"),
            )

            st.write(
                "**Final Decision:**",
                status,
            )

            st.write(
                "**Reason:**",
                item.get("filter_reason"),
            )

            st.markdown("**Individual Criteria**")

            filter_details = item.get("filter_results", {})

            for criterion, details in filter_details.items():

                if criterion == "geography":
                    continue

                passed = details.get("passed", False)

                st.write(
                    f"{'✅ PASS' if passed else '❌ FAIL'} — "
                    f"{criterion.replace('_', ' ').title()}"
                )

                st.caption(details.get("reason", ""))

            # Geography is informational, never a mandatory rejection.
            geography = filter_details.get("geography", {})

            country = geography.get("channel_country")

            st.caption(
                "Channel country: "
                f"{country if country else 'Not Available'}. "
                "This does not represent audience geography."
            )


else:

    st.info(
        """
        No filtering results are available in this session.

        Click **Evaluate All Influencers** to evaluate
        all channels currently stored in discovery JSON.
        """
    )


# --------------------------------------------------
# DATA QUALITY NOTICE
# --------------------------------------------------

st.divider()

st.subheader("⚠️ Filtering Data Quality")

st.markdown(
    """
    - Hidden or unavailable subscriber counts do not pass.
    - Engagement is calculated only when sufficient recent-video
      statistics are available.
    - Missing statistics are marked unavailable, not estimated.
    - Classification uses actual channel and public video content.
    - PASS means all mandatory configured criteria were met.
    """
)

st.caption(
    "EDXSO Influencer Outreach | Filtering powered by Python"
)
