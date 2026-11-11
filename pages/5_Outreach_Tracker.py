
import pandas as pd
import streamlit as st

from sqlalchemy import func, select

from src.influencer_outreach.database import SessionLocal
from src.influencer_outreach.models import OutreachRecord


st.set_page_config(
    page_title="Outreach Tracker | EDXSO",
    page_icon="📨",
    layout="wide",
)


def load_outreach_data():
    """Load outreach records and their influencer details from SQLite."""

    db = SessionLocal()

    try:
        records = db.scalars(
            select(OutreachRecord)
            .order_by(OutreachRecord.processed_at.desc())
        ).all()

        result = []

        for record in records:
            influencer = record.influencer

            result.append({
                "id": record.id,
                "channel_id": influencer.channel_id,
                "influencer_name": influencer.channel_name,
                "profile_url": influencer.profile_url,
                "recipient_email": record.recipient_email,
                "email_subject": record.email_subject,
                "email_body": record.email_body,
                "status": record.status,
                "dry_run": record.dry_run,
                "sent_at": record.sent_at,
                "processed_at": record.processed_at,
                "error": record.error,
                "message": record.message,
                "personalized_message_id": (
                    record.personalized_message_id
                ),
            })

        return result

    finally:
        db.close()


st.title("📨 Influencer Outreach Tracker")

st.markdown(
    """
    Monitor influencer collaboration outreach, email drafts,
    processing status and sending history.
    """
)

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

with st.sidebar:

    st.subheader("Outreach Tracker")

    st.caption("Data source: SQLite database")

    if st.button("🔄 Refresh Records", width="stretch"):
        st.rerun()

    st.divider()

    st.info(
        """
        This page displays saved outreach history only.

        No emails are automatically sent.
        """
    )


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

try:
    records = load_outreach_data()

except Exception as exc:
    st.error("Unable to load outreach records from SQLite.")
    st.exception(exc)
    st.stop()


if not records:

    st.info(
        "No outreach history is available yet. "
        "Process outreach records to populate this tracker."
    )

    st.stop()


# --------------------------------------------------
# CALCULATE METRICS
# --------------------------------------------------

total_records = len(records)

status_counts = {}

for record in records:
    status = record["status"]
    status_counts[status] = status_counts.get(status, 0) + 1


sent_count = sum(
    record["sent_at"] is not None
    for record in records
)

dry_run_count = sum(
    record["dry_run"] is True
    for record in records
)

skipped_count = sum(
    record["status"].startswith("skipped")
    for record in records
)

duplicate_count = status_counts.get("duplicate", 0)

blocked_count = status_counts.get("blocked", 0)


# --------------------------------------------------
# OVERVIEW
# --------------------------------------------------

st.subheader("📊 Outreach Overview")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Outreach Records", total_records)
col2.metric("Emails Actually Sent", sent_count)
col3.metric("Dry-run Records", dry_run_count)
col4.metric("Skipped Records", skipped_count)

col1, col2, col3 = st.columns(3)

col1.metric("Duplicate Attempts", duplicate_count)
col2.metric("Blocked Attempts", blocked_count)
col3.metric("Unique Influencers", len({
    record["channel_id"] for record in records
}))


# --------------------------------------------------
# STATUS BREAKDOWN
# --------------------------------------------------

st.divider()
st.subheader("📈 Outreach Status Breakdown")

status_df = pd.DataFrame([
    {
        "Status": status,
        "Records": count,
    }
    for status, count in status_counts.items()
])

st.bar_chart(
    status_df.set_index("Status"),
    y="Records",
)

# --------------------------------------------------
# FILTER RECORDS
# --------------------------------------------------

st.divider()
st.subheader("🔍 Search & Filter Outreach")

col1, col2 = st.columns(2)

with col1:
    search_name = st.text_input(
        "Search Influencer",
        placeholder="Enter channel name...",
    )

with col2:
    selected_status = st.selectbox(
        "Filter by Status",
        ["All"] + sorted(status_counts.keys()),
    )


filtered_records = records

if search_name.strip():

    filtered_records = [
        record
        for record in filtered_records
        if search_name.lower()
        in record["influencer_name"].lower()
    ]

if selected_status != "All":

    filtered_records = [
        record
        for record in filtered_records
        if record["status"] == selected_status
    ]


# --------------------------------------------------
# OUTREACH TABLE
# --------------------------------------------------

st.subheader("📋 Outreach History")

table_data = []

for record in filtered_records:

    table_data.append({
        "Influencer": record["influencer_name"],
        "Recipient": record["recipient_email"],
        "Subject": record["email_subject"],
        "Status": record["status"],
        "Dry Run": record["dry_run"],
        "Sent At": record["sent_at"] or "Not Sent",
        "Processed At": record["processed_at"],
        "Profile": record["profile_url"],
    })


if table_data:

    dataframe = pd.DataFrame(table_data)

    st.dataframe(
        dataframe,
        width="stretch",
        hide_index=True,
        column_config={
            "Profile": st.column_config.LinkColumn(
                "Channel Profile",
                display_text="Open Channel",
            ),
            "Dry Run": st.column_config.CheckboxColumn(
                "Dry Run",
                disabled=True,
            ),
        },
    )

    st.caption(
        f"Showing {len(filtered_records)} "
        f"of {total_records} outreach records."
    )

else:

    st.warning("No outreach records match the selected filters.")


# --------------------------------------------------
# INDIVIDUAL OUTREACH DETAILS
# --------------------------------------------------

st.divider()
st.subheader("✉️ Individual Outreach Details")

for record in filtered_records:

    with st.expander(
        f"{record['influencer_name']} — {record['status']}"
    ):

        st.markdown("**Influencer Information**")

        st.write("Channel:", record["influencer_name"])

        st.markdown(
            f"[Open YouTube Profile]({record['profile_url']})"
        )

        st.write(
            "**Recipient:**",
            record["recipient_email"],
        )

        st.write(
            "**Processing Status:**",
            record["status"],
        )

        st.write(
            "**Dry Run:**",
            record["dry_run"],
        )

        st.write(
            "**Sent At:**",
            record["sent_at"] or "Not Sent",
        )

        st.write(
            "**Processed At:**",
            record["processed_at"],
        )

        st.divider()

        st.markdown("**Email Subject**")
        st.write(record["email_subject"])

        st.markdown("**Email Body**")

        st.text_area(
            "Saved Email",
            value=record["email_body"],
            height=180,
            disabled=True,
            key=f"outreach_email_{record['id']}",
        )

        if record["error"]:

            st.error(
                f"Processing issue: {record['error']}"
            )

        if record["message"]:

            st.info(record["message"])

        st.caption(
            "Personalized message database ID: "
            f"{record['personalized_message_id']}"
        )


# --------------------------------------------------
# STATUS SAFETY
# --------------------------------------------------

st.divider()
st.subheader("⚠️ Outreach Safety & Status")

st.markdown(
    """
    - Only publicly listed contact emails may be used for outreach.
    - Missing email addresses remain Not Found.
    - Duplicate outreach attempts are prevented.
    - Dry-run records are not actual sent emails.
    - An email is counted as sent only when a sent timestamp exists.
    - This dashboard is read-only and does not trigger email sending.
    """
)

st.caption(
    "EDXSO Automated Influencer Outreach System | "
    "Outreach tracking powered by SQLite"
)
