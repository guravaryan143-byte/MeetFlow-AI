import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    analytics,
    approvals,
    auth,
    decisions,
    integrations,
    meetings,
    memory,
    notifications,
    tasks,
    transcripts,
)
from app.core.config import settings
from app.db.database import db

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
# Provider clients may use URL query parameters for authentication (for example Trello).
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(
    title="MeetFlow AI API",
    description=(
        "MeetFlow AI — Conversations into commitments. "
        "Cross-Meeting Decision Memory + Human-Controlled Execution."
    ),
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

app.include_router(auth.router)
app.include_router(meetings.router)
app.include_router(transcripts.router)
app.include_router(decisions.router)
app.include_router(tasks.router)
app.include_router(memory.router)
app.include_router(approvals.router)
app.include_router(integrations.router)
app.include_router(notifications.router)
app.include_router(analytics.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }
