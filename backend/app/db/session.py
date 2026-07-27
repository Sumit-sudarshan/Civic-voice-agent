import logging
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from app.config import settings

logger = logging.getLogger(__name__)


# Supabase Postgres everywhere, connected through the Supavisor pooler in
# transaction mode (port 6543 — see settings.DATABASE_URL). Small pool since
# the pooler itself fans out to Postgres; query_cache_size=0 turns off
# SQLAlchemy's statement cache, which is the safe/portable way to avoid
# relying on server-side prepared statements that transaction mode doesn't
# support. pool_recycle keeps connections from going stale against the pooler.
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=300,
    query_cache_size=0,
)

def _run_migrations():
    """
    Lightweight inline migrations. SQLModel's create_all only creates missing
    TABLES — it does NOT add new columns to already-existing tables. We
    handle column additions here. Each ALTER TABLE is wrapped in a try/except
    so it's idempotent on restart.

    The conversational-intake schema (location_address/location_area/
    location_pincode/category, replacing ward/citizen_selected_category/
    location/concerned_person) is a breaking change to the dev DB — there is
    no in-place migration path for it, since the old required fields (ward,
    citizen_selected_category) have no equivalent to backfill from. Drop the
    dev database and let create_all() build the new schema fresh, then
    re-run seed.py. Nothing below needs new entries for that change.
    """
    with engine.connect() as conn:
        # Migration: add pipeline_status column (Phase 2)
        try:
            conn.execute(text(
                "ALTER TABLE complaint ADD COLUMN pipeline_status TEXT NOT NULL DEFAULT 'done'"
            ))
            conn.commit()
            logger.info("Migration applied: complaint.pipeline_status column added")
        except (OperationalError, ProgrammingError):
            # Column already exists — this is the normal path after first run
            conn.rollback()

        # Migration: human_corrected_fields — audit trail for the feedback
        # loop actually writing back to the record (see api/complaints.py's
        # submit_extraction_feedback), not just capturing it for later eval.
        try:
            conn.execute(text(
                "ALTER TABLE complaint ADD COLUMN human_corrected_fields TEXT"
            ))
            conn.commit()
            logger.info("Migration applied: complaint.human_corrected_fields column added")
        except (OperationalError, ProgrammingError):
            conn.rollback()

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    _run_migrations()

def get_session():
    with Session(engine) as session:
        yield session
