"""Main API router combining versioned endpoints."""

from fastapi import APIRouter
from backend.app.routes import health, documents, query, auth

api_router = APIRouter()

# Include routes under /api/v1
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(query.router)
api_router.include_router(auth.router)
