
import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv()


# Read database URL from .env.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./influencer_outreach.db",
).strip()


if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not configured.")


# SQLite-specific connection settings.
connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False


# Create SQLAlchemy engine.
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


# Base class for all database models.
class Base(DeclarativeBase):
    pass


# Create reusable database sessions.
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Provide a database session and close it after use."""

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    """Check whether the database connection works."""

    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT 1")
            )
            return result.scalar_one() == 1

    except Exception as exc:
        raise RuntimeError(
            f"Database connection failed: {exc}"
        ) from exc


def init_db() -> None:
    """Create all registered database tables."""

    # Import models so SQLAlchemy knows about their tables.
    from src.influencer_outreach import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def close_db() -> None:
    """Dispose of the database engine."""

    engine.dispose()
