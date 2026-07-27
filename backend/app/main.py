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

# Allow the frontend to call the API.
#
# `allow_origins=["*"]` together with `allow_credentials=True` is not the
# no-op it looks like: Starlette echoes the caller's own Origin back (it must,
# since browsers reject a literal "*" on credentialed responses), so *any*
# site could have made credentialed cross-origin calls with the session
# cookie. That was only ever mitigated by the cookie's SameSite=Lax. In
# production the frontend and API are same-origin behind the same Nginx, so
# nothing legitimate needs the wildcard.
#
# Default is now: explicit localhost dev origins, plus a regex for the
# project's ephemeral Cloudflare quick-tunnel hostnames (which change on every
# `cloudflared` restart by design — see MVP_Design.md §3.1 — so pinning one
# exact URL here would mean a code change after every tunnel restart).
# ALLOWED_ORIGINS still overrides both when set explicitly.
_DEV_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
    "http://localhost:3000", "http://127.0.0.1:3000",
]
if settings.ALLOWED_ORIGINS and settings.ALLOWED_ORIGINS != "*":
    _origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    _origin_regex = None
else:
    _origins = _DEV_ORIGINS
    _origin_regex = r"https://[a-z0-9-]+\.trycloudflare\.com"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
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
def health_check(session: Session = Depends(get_session)):
    """
    Doubles as Phase 7's Supabase keep-alive target (GitHub Actions cron
    pings this on a schedule to defeat Supabase's 7-day inactivity pause) —
    that only works if the ping actually touches the database, which this
    endpoint didn't do before. The DB touch is best-effort and never turns
    a healthy process into a reported failure: a DB hiccup is logged, not
    surfaced as a non-200, since CI's post-deploy smoke check and the GCP
    uptime check both key off this endpoint staying up through transient DB
    blips that aren't really "the app is down."

    Deliberately a plain `def`, not `async def`: `session.exec()` is a
    blocking network round-trip to Supabase, and an `async def` endpoint runs
    directly on the event loop — a slow or hung DB would have stalled every
    other in-flight request on this single-worker VM for up to the pool's
    30s checkout timeout. As a sync endpoint FastAPI runs it in the
    threadpool, so a stuck health check can't take the app down with it.
    """
    db_ok = True
    try:
        session.exec(select(1))
    except Exception as e:
        db_ok = False
        logger.warning(f"/health DB touch failed: {e}")
    return {"status": "ok", "db_reachable": db_ok}

