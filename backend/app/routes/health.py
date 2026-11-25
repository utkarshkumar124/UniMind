"""Health and readiness check routes for UniMind service monitoring."""

from fastapi import APIRouter, HTTPException, status
from backend.app.core.config import settings
from backend.app.models.schemas import HealthResponse
from backend.app.rag.embedder import (
    EmbeddingModelManager,
    EMBEDDING_STATE_READY,
    EMBEDDING_STATE_FAILED,
)

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Service Health Check")
async def health_check() -> HealthResponse:
    """Return current operational and embedding readiness status of the UniMind backend."""
    manager = EmbeddingModelManager()
    emb_status = manager.status
    emb_error = manager.error

    if emb_status == EMBEDDING_STATE_READY:
        overall_status = "healthy"
    elif emb_status == EMBEDDING_STATE_FAILED:
        overall_status = "unhealthy"
    else:
        overall_status = "initializing"

    return HealthResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        embedding_status=emb_status,
        embedding_error=emb_error,
    )


@router.get("/ready", response_model=HealthResponse, summary="Service Readiness Check")
async def readiness_check() -> HealthResponse:
    """Return 200 only when the backend and embedding model are READY to serve queries."""
    health = await health_check()
    if health.embedding_status != EMBEDDING_STATE_READY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service not ready (embedding_status={health.embedding_status})",
        )
    return health
