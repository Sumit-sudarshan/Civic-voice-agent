import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from app.utils.logging import configure_logging

# Must run before any other app.* module logs anything — attaches the JSON
# formatter (and, on the VM, a Cloud Logging handler) to the root logger.
# See utils/logging.py: previously nothing imported that module at all, so
# every INFO-level log in the app was silently dropped in production.
configure_logging()

from app.api import complaints, suggestions, stats, settings as settings_api, eval as eval_api, intake, auth as auth_api, leaders as leaders_api
from app.config import settings
from app.db.session import create_db_and_tables, get_session
from app.pipeline.orchestrator import resume_stuck_pipelines

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    resume_stuck_pipelines()
    yield

app = FastAPI(title="Civic Voice Agent", lifespan=lifespan)

# Allow frontend to call the API. ALLOWED_ORIGINS defaults to "*" for local
# dev; set it to the deployed frontend's exact origin(s) in production.
_origins = settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(complaints.router)
app.include_router(suggestions.router)
app.include_router(stats.router)
app.include_router(settings_api.router)
app.include_router(eval_api.router)
app.include_router(intake.router)
app.include_router(auth_api.router)
app.include_router(leaders_api.router)

@app.get("/health")
async def health_check(session: Session = Depends(get_session)):
    """
    Doubles as Phase 7's Supabase keep-alive target (GitHub Actions cron
    pings this on a schedule to defeat Supabase's 7-day inactivity pause) —
    that only works if the ping actually touches the database, which this
    endpoint didn't do before. The DB touch is best-effort and never turns
    a healthy process into a reported failure: a DB hiccup is logged, not
    surfaced as a non-200, since CI's post-deploy smoke check and the GCP
    uptime check both key off this endpoint staying up through transient DB
    blips that aren't really "the app is down."
    """
    db_ok = True
    try:
        session.exec(select(1))
    except Exception as e:
        db_ok = False
        logger.warning(f"/health DB touch failed: {e}")
    return {"status": "ok", "db_reachable": db_ok}

