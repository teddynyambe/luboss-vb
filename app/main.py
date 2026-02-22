from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, admin, chairman, treasurer, compliance, member, ai
from app.services.scheduler import start_scheduler, stop_scheduler
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Get logger for this module
logger = logging.getLogger(__name__)
logger.info("Starting Luboss95 Village Banking v2 API")


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Luboss95 Village Banking v2 API",
    description="LUBOSS 95 Village Banking System",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],  # Frontend URLs - allow all for dev
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(chairman.router)
app.include_router(treasurer.router)
app.include_router(compliance.router)
app.include_router(member.router)
app.include_router(ai.router)


@app.get("/")
def root():
    """Root endpoint."""
    return {"message": "Luboss95 Village Banking v2 API", "version": "2.0.0"}


@app.get("/api/health")
def health_check():
    """Health check endpoint — checks API and database connectivity."""
    from app.db.base import get_db
    from sqlalchemy import text
    from datetime import datetime, timezone

    db_status = "unreachable"
    db_error = None
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_error = str(e)

    status = "healthy" if db_status == "connected" else "degraded"

    return {
        "status": status,
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "api": "ok",
            "database": db_status,
        },
        **({"database_error": db_error} if db_error else {})
    }
