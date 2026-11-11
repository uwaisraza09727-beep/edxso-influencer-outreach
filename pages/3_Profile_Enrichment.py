
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.influencer_outreach.database import SessionLocal
from src.influencer_outreach.services.enrichment import (
    enrich_influencers,
    save_enriched_records,
)
from src.influencer_outreach.repositories.influencer_repository import (
    save_enrichment_records as save_enrichment_database,
)


st.set_page_config(
    page_title="Profile Enrichment | EDXSO",
    page_icon="📧",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FILTERED_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "filtered_influencers.json"
)

ENRICHED_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "enriched_influencers.json"
)


def load_filtered_records():
    """Load the latest filtered influencer snapshot."""

    if not FILTERED_FILE.exists():
        raise FileNotFoundError(
            "Filtered data not found. Run Influencer Filtering first."
        )

    data = json.loads(
        FILTERED_FILE.read_text(encoding="utf-8")
    )

    records = data.get("records", [])

    if not isinstance(records, list):
        raise ValueError("Filtered records must be a list.")

    channel_ids = [
        record.get("channel_id")
        for record in records
    ]

    if not channel_ids or None in channel_ids:
        raise ValueError("Some influencer records are missing channel IDs.")

    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError("Duplicate channel IDs found in filtered data.")

    return records


st.title("📧 Influencer Profile Enrichment")

st.markdown(
    """
    Extract publicly available contact information, websites,
    social profile links and content themes from influencer data.
    """
)

# --------------------------------------------------
# LOAD SOURCE DATA
# --------------------------------------------------

try:
    source_records = load_filtered_records()

except Exception as exc:
    st.error(f"Unable to load filtered influencer data: {exc}")
    st.stop()


pass_count = sum(
    record.get("filter_status") == "PASS"
    for record in source_records
)

fail_count = sum(
    record.get("filter_status") == "FAIL"
    for record in source_records
)

st.subheader("📊 Source Data Overview")

col1, col2, col3 = st.columns(3)

col1.metric("Total Discovered Profiles", len(source_records))
col2.metric("Qualified Profiles", pass_count)
col3.metric("Not Qualified Profiles", fail_count)

st.info(
    """
    **Enrichment sources and data rules**

    - Channel descriptions: public contact emails and links.
    - Public video descriptions: separate email candidates.
    - Website and social profile links are extracted from
      channel descriptions.
    - Social profile ownership is not independently verified.
    - Audience demographics remain Not Available.
    - Email deliverability is not verified.
    """
)

st.caption(
    "This page processes existing local data. "
    "No new YouTube API requests are made."
)

# --------------------------------------------------
# RUN ENRICHMENT
# --------------------------------------------------

st.subheader("🚀 Run Profile Enrichment")

if st.button(
    "📧 Enrich All Influencer Profiles",
    type="primary",
    use_container_width=True,
):

    database = None

    try:
        with st.spinner(
            "Extracting publicly available influencer information..."
        ):

            # 1. Enrich all filtered channel records.
            enriched_records = enrich_influencers(
                source_records
            )

            if len(enriched_records) != len(source_records):
                raise ValueError(
                    "Enrichment record count does not match source count."
                )

            # 2. Validate required contact fields.
            for record in enriched_records:
                if not record.get("contact_email"):
                    raise ValueError(
                        "A mandatory contact_email field is missing."
                    )

            # 3. Save enriched JSON snapshot.
            json_path = save_enriched_records(
                enriched_records,
                output_path=ENRICHED_FILE,
            )

            # 4. Save or update SQLite enrichment records.
            database = SessionLocal()

            try:
                database_result = save_enrichment_database(
                    database,
                    enriched_records,
                )

                database.commit()

            except Exception:
                database.rollback()
                raise

            finally:
                database.close()
                database = None

            # 5. Calculate verified enrichment statistics.
            emails_found = sum(
                record.get("email_status") == "publicly_listed"
                for record in enriched_records
            )

            emails_not_found = sum(
                record.get("email_status") == "not_found"
                for record in enriched_records
            )

            websites_found = sum(
                bool(record.get("website_urls"))
                for record in enriched_records
            )

            social_profiles_found = sum(
                bool(record.get("social_media_links"))
                for record in enriched_records
            )

            st.session_state["enrichment_results"] = (
                enriched_records
            )

            st.session_state["enrichment_summary"] = {
                "total": len(enriched_records),
                "emails_found": emails_found,
                "emails_not_found": emails_not_found,
                "websites_found": websites_found,
                "social_profiles_found": social_profiles_found,
                "json_path": str(json_path),
                "database": database_result,
            }

        st.success(
            "Influencer profile enrichment completed successfully."
        )

    except Exception as exc:
        st.error(
            "Profile enrichment failed. "
            "Review the error details below."
        )
        st.exception(exc)

    finally:
        if database is not None:
            database.close()


# --------------------------------------------------
# ENRICHMENT SUMMARY
# --------------------------------------------------

results = st.session_state.get("enrichment_results")
summary = st.session_state.get("enrichment_summary")

if summary:

    st.divider()
    st.subheader("✅ Enrichment Summary")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Profiles Enriched", summary["total"])
    col2.metric("Public Emails Found", summary["emails_found"])
    col3.metric("Emails Not Found", summary["emails_not_found"])
    col4.metric("Websites Found", summary["websites_found"])

    st.metric(
        "Social Profiles Identified",
        summary["social_profiles_found"],
    )

    st.subheader("🗄️ SQLite Database Results")

    database_result = summary["database"]

    db_col1, db_col2, db_col3 = st.columns(3)

    db_col1.metric(
        "New Records",
        database_result["inserted"],
    )

    db_col2.metric(
        "Updated Records",
        database_result["updated"],
    )

    db_col3.metric(
        "Skipped Records",
        database_result["skipped"],
    )

    st.write("**JSON output:**", summary["json_path"])

    # --------------------------------------------------
    # EMAIL AVAILABILITY CHART
    # --------------------------------------------------

    st.divider()
    st.subheader("📊 Email Availability")

    email_df = pd.DataFrame([
        {
            "Email Status": "Publicly Listed",
            "Profiles": summary["emails_found"],
        },
        {
            "Email Status": "Not Found",
            "Profiles": summary["emails_not_found"],
        },
    ])

    st.bar_chart(
        email_df.set_index("Email Status"),
        y="Profiles",
    )

    # --------------------------------------------------
    # ENRICHMENT RESULTS TABLE
    # --------------------------------------------------

    st.divider()
    st.subheader("👥 Enriched Influencer Profiles")

    table_data = []

    for record in results:

        social_links = record.get("social_media_links", {})

        platforms = ", ".join(
            social_links.keys()
        ) if isinstance(social_links, dict) else ""

        table_data.append({
            "Influencer": record.get("channel_name"),
            "Email": record.get("contact_email"),
            "Email Status": record.get("email_status"),
            "Website": record.get("website"),
            "Social Platforms": platforms or "Not Found",
            "Classification": record.get(
                "classification_category"
            ),
            "Filter Status": record.get("filter_status"),
            "Channel Profile": record.get("profile_url"),
        })

    table_df = pd.DataFrame(table_data)

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Channel Profile": st.column_config.LinkColumn(
                "Channel Profile",
                display_text="Open Channel",
            ),
            "Website": st.column_config.LinkColumn(
                "Website",
                display_text="Open Website",
            ),
        },
    )

    # --------------------------------------------------
    # INDIVIDUAL ENRICHMENT DETAILS
    # --------------------------------------------------

    st.divider()
    st.subheader("🔍 Individual Profile Details")

    for record in results:

        channel_name = record.get(
            "channel_name",
            "Unknown Influencer",
        )

        with st.expander(channel_name):

            st.write(
                "**Contact Email:**",
                record.get("contact_email", "Not Found"),
            )

            st.write(
                "**Email Status:**",
                record.get("email_status", "Not Available"),
            )

            st.caption(
                record.get("email_verification_note", "")
            )

            st.markdown("**Public Email Sources**")

            for source in record.get("email_sources", []):

                st.write(
                    source.get("email", "Not Available"),
                    "|",
                    source.get("source_type", ""),
                    "|",
                    source.get("source_url", ""),
                )

            st.markdown("**Public Email Candidates from Videos**")

            candidates = record.get(
                "public_email_candidates",
                [],
            )

            if candidates:
                for candidate in candidates:
                    st.write(
                        candidate.get("email"),
                        "|",
                        candidate.get("source_url"),
                        "| Ownership:",
                        candidate.get("ownership_status"),
                    )
            else:
                st.write("No public video email candidates found.")

            st.markdown("**Websites**")

            for website in record.get("website_urls", []):
                st.write(website)

            st.markdown("**Social Media Profiles**")

            social_links = record.get(
                "social_media_links",
                {},
            )

            if social_links:
                for platform, links in social_links.items():
                    st.write(f"**{platform}:**")

                    for link in links:
                        st.markdown(f"- [{link}]({link})")
            else:
                st.write("No social profiles found.")

            st.markdown("**Content Themes**")

            themes = record.get("content_themes", [])

            st.write(
                ", ".join(themes)
                if themes
                else "Not Available"
            )

            st.markdown("**Audience Demographics**")

            st.json(
                record.get("audience_demographics", {})
            )


else:

    st.info(
        """
        No enrichment results have been generated in this session.

        Click **Enrich All Influencer Profiles** to process
        the latest filtered influencer records.
        """
    )


# --------------------------------------------------
# DATA QUALITY NOTICE
# --------------------------------------------------

st.divider()

st.subheader("⚠️ Data Quality & Privacy Rules")

st.markdown(
    """
    - Contact emails are extracted only from public channel descriptions.
    - Emails in video descriptions are kept separately as candidates.
    - No email addresses are guessed or fabricated.
    - Publicly listed does not mean mailbox deliverability verified.
    - Social profile ownership is not independently confirmed.
    - Audience demographics are not invented.
    - Missing contact information is explicitly marked Not Found.
    """
)

st.caption(
    "EDXSO Influencer Outreach | "
    "Profile Enrichment powered by Python and public data"
)
