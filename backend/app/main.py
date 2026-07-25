from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import complaints, suggestions, stats, settings as settings_api, eval as eval_api, intake
from app.config import settings
from app.db.session import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
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

@app.get("/health")
async def health_check():
    return {"status": "ok"}

