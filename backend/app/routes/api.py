"""Main API router combining versioned endpoints."""

from fastapi import APIRouter
from backend.app.routes import health, documents

api_router = APIRouter()

# Include routes under /api/v1
api_router.include_router(health.router)
api_router.include_router(documents.router)

