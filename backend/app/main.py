from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import complaints, suggestions, stats, settings, eval as eval_api, intake
from app.db.session import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(title="Civic Voice Agent", lifespan=lifespan)

# Allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(complaints.router)
app.include_router(suggestions.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(eval_api.router)
app.include_router(intake.router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

