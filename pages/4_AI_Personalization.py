
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.influencer_outreach.database import SessionLocal
from src.influencer_outreach.services.personalization import (
    EMAIL_MIN_WORDS,
    EMAIL_MAX_WORDS,
    DM_MIN_WORDS,
    DM_MAX_WORDS,
    generate_messages_for_influencers,
    save_personalized_messages as save_messages_json,
)
from src.influencer_outreach.repositories.outreach_repository import (
    save_personalized_messages as save_messages_database,
    get_personalized_messages,
)


st.set_page_config(
    page_title="AI Personalization | EDXSO",
    page_icon="🤖",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ENRICHED_FILE = (
    PROJECT_ROOT / "data" / "processed" / "enriched_influencers.json"
)

MESSAGES_FILE = (
    PROJECT_ROOT / "data" / "processed" / "personalized_messages.json"
)

DEFAULT_VALUE_PROPOSITION = (
    "Explore a relevant collaboration that offers your audience "
    "practical and useful technology and AI learning content."
)


def load_enriched_records():
    """Load enriched influencer records."""

    if not ENRICHED_FILE.exists():
        raise FileNotFoundError(
            "Enriched data not found. Run Profile Enrichment first."
        )

    data = json.loads(
        ENRICHED_FILE.read_text(encoding="utf-8")
    )

    records = data.get("records", [])

    if not isinstance(records, list):
        raise ValueError("Enriched records must be a list.")

    return records


def load_existing_messages():
    """Load existing successful JSON drafts."""

    if not MESSAGES_FILE.exists():
        return []

    data = json.loads(
        MESSAGES_FILE.read_text(encoding="utf-8")
    )

    return data.get("messages", [])


def load_messages_from_database():
    """Load all permanently saved drafts from SQLite."""

    db = SessionLocal()

    try:
        saved_records = get_personalized_messages(db)

        messages = []

        for item in saved_records:
            influencer = item.influencer

            messages.append({
                "channel_id": influencer.channel_id,
                "influencer_name": influencer.channel_name,
                "platform": influencer.platform,
                "profile_url": influencer.profile_url,
                "email_subject": item.email_subject,
                "email_pitch": item.email_pitch,
                "email_word_count": item.email_word_count,
                "instagram_dm": item.instagram_dm,
                "instagram_dm_word_count": (
                    item.instagram_dm_word_count
                ),
                "generation_status": item.generation_status,
                "generation_model": item.generation_model,
                "generation_attempts": item.generation_attempts,
                "source_evidence": item.source_evidence or {},
                "generated_at": str(item.generated_at),
            })

        return messages

    finally:
        db.close()


st.title("🤖 AI Influencer Personalization")

st.markdown(
    """
    Generate personalized collaboration emails and Instagram
    direct messages using Gemini AI for qualified influencers.
    """
)

# --------------------------------------------------
# LOAD ENRICHED DATA
# --------------------------------------------------

try:
    enriched_records = load_enriched_records()

except Exception as exc:
    st.error(f"Unable to load enriched records: {exc}")
    st.stop()


qualified_records = [
    record
    for record in enriched_records
    if record.get("filter_status") == "PASS"
]

st.subheader("📊 Personalization Overview")

col1, col2, col3 = st.columns(3)

col1.metric("Total Enriched Profiles", len(enriched_records))
col2.metric("Qualified Influencers", len(qualified_records))
col3.metric(
    "Not Qualified",
    len(enriched_records) - len(qualified_records),
)

st.info(
    f"""
    **Message requirements**

    - Email body: {EMAIL_MIN_WORDS}–{EMAIL_MAX_WORDS} words.
    - Instagram DM: {DM_MIN_WORDS}–{DM_MAX_WORDS} words.
    - Maximum generation attempts: 3.
    - AI provider: Gemini.
    - Only PASS influencers are eligible.
    """
)

st.caption(
    "This module generates drafts only. It does not send "
    "emails or Instagram messages."
)

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

st.subheader("⚙️ Personalization Configuration")

brand_value_proposition = st.text_area(
    "Collaboration Value Proposition",
    value=DEFAULT_VALUE_PROPOSITION,
    height=100,
    help="Describe the genuine value offered to creators.",
)

if qualified_records:

    preview_df = pd.DataFrame([
        {
            "Influencer": record.get("channel_name"),
            "Category": record.get("classification_category"),
            "Filter Status": record.get("filter_status"),
            "Profile": record.get("profile_url"),
        }
        for record in qualified_records
    ])

    with st.expander("View eligible influencers"):
        st.dataframe(
            preview_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Profile": st.column_config.LinkColumn(
                    "Profile",
                    display_text="Open Channel",
                )
            },
        )


# --------------------------------------------------
# GENERATE NEW MESSAGES
# --------------------------------------------------

st.subheader("🚀 Generate Personalized Messages")

if not qualified_records:
    st.warning(
        "No qualified influencers found. Run Filtering first."
    )

elif st.button(
    "✨ Generate AI Messages",
    type="primary",
    width="stretch",
    disabled=not brand_value_proposition.strip(),
):

    try:
        with st.spinner(
            "Gemini is generating personalized collaboration messages..."
        ):

            generation_result = generate_messages_for_influencers(
                records=qualified_records,
                brand_value_proposition=brand_value_proposition.strip(),
            )

            new_messages = generation_result["messages"]
            errors = generation_result["errors"]

            if new_messages:

                # Save new drafts to SQLite first.
                db = SessionLocal()

                try:
                    database_result = save_messages_database(
                        db,
                        new_messages,
                    )
                    db.commit()

                except Exception:
                    db.rollback()
                    raise

                finally:
                    db.close()

                # Preserve previous JSON messages.
                existing_messages = load_existing_messages()

                merged_messages = {
                    item["channel_id"]: item
                    for item in existing_messages
                    if item.get("channel_id")
                }

                for item in new_messages:
                    merged_messages[item["channel_id"]] = item

                final_messages = list(
                    merged_messages.values()
                )

                json_result = {
                    "total_qualified": len(qualified_records),
                    "messages": final_messages,
                    "errors": errors,
                }

                json_path = save_messages_json(
                    json_result,
                    output_path=MESSAGES_FILE,
                )

                st.session_state["personalization_summary"] = {
                    "generated": len(new_messages),
                    "failed": len(errors),
                    "total_qualified": len(qualified_records),
                    "database": database_result,
                    "json_path": str(json_path),
                    "errors": errors,
                }

                st.success(
                    f"{len(new_messages)} personalized drafts saved."
                )

            else:
                st.warning(
                    "No new drafts were generated. "
                    "Existing saved drafts have been preserved."
                )

                st.session_state["personalization_errors"] = errors

    except Exception as exc:
        st.error("Message generation could not be completed.")
        st.exception(exc)


# --------------------------------------------------
# GENERATION SUMMARY
# --------------------------------------------------

summary = st.session_state.get("personalization_summary")

if summary:

    st.divider()
    st.subheader("✅ Latest Generation Summary")

    col1, col2, col3 = st.columns(3)

    col1.metric("Successfully Generated", summary["generated"])
    col2.metric("Generation Failures", summary["failed"])
    col3.metric("Total Qualified", summary["total_qualified"])

    st.subheader("🗄️ SQLite Database Results")

    database_result = summary["database"]

    col1, col2, col3 = st.columns(3)

    col1.metric("New Records", database_result["inserted"])
    col2.metric("Updated Records", database_result["updated"])
    col3.metric("Skipped Records", database_result["skipped"])

    st.write("**JSON output:**", summary["json_path"])

    if summary["errors"]:
        with st.expander("Generation Errors"):
            for error in summary["errors"]:
                st.write(
                    error.get("influencer_name", "Unknown"),
                    "|",
                    error.get("error_type"),
                    "|",
                    error.get("error"),
                )


# --------------------------------------------------
# PERMANENTLY LOAD SAVED DATABASE DRAFTS
# --------------------------------------------------

st.divider()
st.subheader("📨 Saved Personalized Messages")

try:
    saved_messages = load_messages_from_database()

except Exception as exc:
    st.error(f"Unable to load saved messages from SQLite: {exc}")
    saved_messages = []

if saved_messages:

    st.success(
        f"{len(saved_messages)} personalized drafts loaded from SQLite."
    )

    search_name = st.text_input(
        "Search Influencer",
        placeholder="Enter channel name...",
    )

    if search_name.strip():
        displayed_messages = [
            item
            for item in saved_messages
            if search_name.lower()
            in item["influencer_name"].lower()
        ]
    else:
        displayed_messages = saved_messages

    for message in displayed_messages:

        channel_name = message["influencer_name"]
        channel_id = message["channel_id"]

        with st.expander(
            f"✉️ {channel_name} — "
            f"{message['email_word_count']} email words",
            expanded=False,
        ):

            st.markdown("**Influencer Profile**")

            st.markdown(
                f"[Open YouTube Channel]({message['profile_url']})"
            )

            st.caption(f"Channel ID: {channel_id}")

            st.divider()

            st.markdown("**Email Subject**")
            st.write(message["email_subject"])

            st.markdown(
                f"**Email Body — {message['email_word_count']} words**"
            )

            st.text_area(
                "Saved Email Draft",
                value=message["email_pitch"],
                height=190,
                disabled=True,
                key=f"saved_email_{channel_id}",
            )

            st.divider()

            st.markdown(
                f"**Instagram DM — "
                f"{message['instagram_dm_word_count']} words**"
            )

            st.text_area(
                "Saved Instagram Draft",
                value=message["instagram_dm"],
                height=110,
                disabled=True,
                key=f"saved_dm_{channel_id}",
            )

            st.caption(
                f"Status: {message['generation_status']} | "
                f"Model: {message['generation_model']} | "
                f"Attempts: {message['generation_attempts']}"
            )

            with st.expander("Source Evidence"):
                st.json(message["source_evidence"])

else:

    st.info(
        "No personalized messages have been saved in SQLite yet."
    )


# --------------------------------------------------
# DATA QUALITY AND SAFETY
# --------------------------------------------------

st.divider()

st.subheader("⚠️ AI Personalization Safety")

st.markdown(
    """
    - Messages are generated only for PASS influencers.
    - Personalization uses collected public channel content.
    - No audience demographics or achievements are invented.
    - Email and DM word counts are validated.
    - Invalid responses are retried up to three times.
    - Previous successful drafts are preserved.
    - Saved drafts are loaded from SQLite.
    - Generated messages are drafts, not sent communications.
    - No automatic email or Instagram messaging is performed.
    """
)

st.caption(
    "EDXSO Influencer Outreach | "
    "AI Personalization powered by Gemini and SQLite"
)
