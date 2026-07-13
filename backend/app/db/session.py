import logging
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from app.config import settings

logger = logging.getLogger(__name__)

# We use SQLite so we set check_same_thread=False
sqlite_url = f"sqlite:///{settings.DB_PATH}"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def _run_migrations():
    """
    Lightweight inline migrations for SQLite.
    SQLModel's create_all only creates missing TABLES — it does NOT add new
    columns to already-existing tables. We handle column additions here.
    Each ALTER TABLE is wrapped in a try/except so it's idempotent on restart.

    The conversational-intake schema (location_address/location_area/
    location_pincode/category, replacing ward/citizen_selected_category/
    location/concerned_person) is a breaking change to the dev DB — there is
    no in-place migration path for it, since the old required fields (ward,
    citizen_selected_category) have no equivalent to backfill from. Delete
    the dev SQLite file and let create_all() build the new schema fresh, then
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
        except Exception:
            # Column already exists — this is the normal path after first run
            pass

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    _run_migrations()

def get_session():
    with Session(engine) as session:
        yield session
