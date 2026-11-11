
import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from src.influencer_outreach.database import SessionLocal
from src.influencer_outreach.models import (
    Influencer,
    InfluencerEnrichment,
    FilteringResult,
    PersonalizedMessage,
    OutreachRecord,
)


st.set_page_config(
    page_title="EDXSO Influencer Outreach",
    page_icon="📢",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_count(db, model, condition=None):
    """Return the number of records in a database table."""
    statement = select(func.count()).select_from(model)

    if condition is not None:
        statement = statement.where(condition)

    return db.scalar(statement) or 0


def load_dashboard_data():
    """Load dashboard statistics and charts from SQLite."""
    db = SessionLocal()

    try:
        stats = {
            "total_influencers": get_count(db, Influencer),
            "qualified": get_count(
                db,
                FilteringResult,
                FilteringResult.filter_status == "PASS",
            ),
            "failed": get_count(
                db,
                FilteringResult,
                FilteringResult.filter_status == "FAIL",
            ),
            "enriched": get_count(db, InfluencerEnrichment),
            "public_emails": get_count(
                db,
                InfluencerEnrichment,
                InfluencerEnrichment.email_status == "publicly_listed",
            ),
            "not_found_emails": get_count(
                db,
                InfluencerEnrichment,
                InfluencerEnrichment.email_status == "not_found",
            ),
            "personalized_messages": get_count(
                db, PersonalizedMessage
            ),
            "outreach_records": get_count(db, OutreachRecord),
            "sent_emails": get_count(
                db,
                OutreachRecord,
                OutreachRecord.sent_at.is_not(None),
            ),
            "dry_run_records": get_count(
                db,
                OutreachRecord,
                OutreachRecord.dry_run.is_(True),
            ),
        }

        category_rows = db.execute(
            select(
                FilteringResult.classification_category,
                func.count(),
            )
            .group_by(FilteringResult.classification_category)
            .order_by(func.count().desc())
        ).all()

        email_rows = db.execute(
            select(
                InfluencerEnrichment.email_status,
                func.count(),
            )
            .group_by(InfluencerEnrichment.email_status)
            .order_by(func.count().desc())
        ).all()

        outreach_rows = db.execute(
            select(
                OutreachRecord.status,
                func.count(),
            )
            .group_by(OutreachRecord.status)
            .order_by(func.count().desc())
        ).all()

        recent_rows = db.execute(
            select(
                Influencer.channel_name.label("Influencer"),
                Influencer.platform.label("Platform"),
                Influencer.subscriber_count.label("Subscribers"),
                FilteringResult.classification_category.label("Category"),
                FilteringResult.filter_status.label("Filter Status"),
                Influencer.profile_url.label("Profile"),
            )
            .outerjoin(
                FilteringResult,
                FilteringResult.influencer_id == Influencer.id,
            )
            .order_by(Influencer.updated_at.desc())
            .limit(10)
        ).mappings().all()

        return {
            "stats": stats,
            "categories": [
                {
                    "Category": category or "Unclassified",
                    "Influencers": count,
                }
                for category, count in category_rows
            ],
            "emails": [
                {
                    "Email Status": status or "Unknown",
                    "Profiles": count,
                }
                for status, count in email_rows
            ],
            "outreach": [
                {
                    "Outreach Status": status or "Unknown",
                    "Records": count,
                }
                for status, count in outreach_rows
            ],
            "recent": [dict(row) for row in recent_rows],
        }

    finally:
        db.close()


# ---------------- MAIN DASHBOARD ----------------

st.title("📢 EDXSO Automated Influencer Outreach System")

st.markdown(
    """
    Discover, evaluate, enrich, and manage technology and AI
    micro-influencers using automated outreach workflows.
    """
)

# Sidebar
with st.sidebar:
    st.title("EDXSO")
    st.caption("Influencer Outreach Platform")

    st.divider()

    st.subheader("Current Configuration")
    st.write("**Niche:** Technology & AI")
    st.write("**Platform:** YouTube")
    st.write("**Followers:** 5,000–100,000")
    st.write("**AI Provider:** Gemini")

    st.divider()

    if st.button("🔄 Refresh Dashboard", use_container_width=True):
        st.rerun()

    st.caption("Data source: Local SQLite database")

# Load database data
try:
    dashboard = load_dashboard_data()
    stats = dashboard["stats"]

except Exception as exc:
    st.error("Unable to load dashboard data from SQLite.")
    st.exception(exc)
    st.stop()


# Main metrics
st.subheader("📊 Dashboard Overview")

total = stats["total_influencers"]
qualified = stats["qualified"]
qualification_rate = (
    (qualified / total) * 100 if total else 0
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Influencers", total)
col2.metric("Qualified Influencers", qualified)
col3.metric("Qualification Rate", f"{qualification_rate:.1f}%")
col4.metric("Failed Filters", stats["failed"])

st.divider()

# Enrichment and outreach metrics
st.subheader("📬 Enrichment & Outreach")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Enriched Profiles", stats["enriched"])
col2.metric("Public Emails Found", stats["public_emails"])
col3.metric("AI Messages Generated", stats["personalized_messages"])
col4.metric("Outreach Records", stats["outreach_records"])

col1, col2, col3 = st.columns(3)

col1.metric("Emails Not Found", stats["not_found_emails"])
col2.metric("Emails Actually Sent", stats["sent_emails"])
col3.metric("Dry-run Records", stats["dry_run_records"])

st.divider()

# Charts
st.subheader("📈 Data Analytics")

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("**Influencer Classification**")

    category_df = pd.DataFrame(dashboard["categories"])

    if not category_df.empty:
        st.bar_chart(
            category_df.set_index("Category"),
            y="Influencers",
        )
    else:
        st.info("No classification data available.")

with chart_col2:
    st.markdown("**Public Email Availability**")

    email_df = pd.DataFrame(dashboard["emails"])

    if not email_df.empty:
        st.bar_chart(
            email_df.set_index("Email Status"),
            y="Profiles",
        )
    else:
        st.info("No email enrichment data available.")

st.divider()

# Outreach analysis
st.subheader("📨 Outreach Status")

outreach_df = pd.DataFrame(dashboard["outreach"])

if not outreach_df.empty:
    st.bar_chart(
        outreach_df.set_index("Outreach Status"),
        y="Records",
    )
else:
    st.info("No outreach records available.")

st.divider()

# Recent influencer table
st.subheader("👥 Recent Influencer Profiles")

recent_df = pd.DataFrame(dashboard["recent"])

if not recent_df.empty:
    st.dataframe(
        recent_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Profile": st.column_config.LinkColumn(
                "Channel Profile",
                display_text="Open Profile",
            ),
            "Subscribers": st.column_config.NumberColumn(
                "Subscribers",
                format="%d",
            ),
        },
    )
else:
    st.info("No influencer profiles available.")

st.divider()

# Data quality notice
st.subheader("⚠️ Data Quality & Safety")

st.info(
    """
    - Only publicly available influencer information is used.
    - Missing email addresses are marked as Not Found.
    - Audience demographics are not assumed or fabricated.
    - Outreach is currently operating in dry-run mode.
    - No actual emails have been sent.
    """
)

st.caption(
    "EDXSO Automated Influencer Outreach System | "
    "Powered by Python, Streamlit, SQLite and Gemini"
)
