"""UniMind FastAPI Application Entry Point."""

import time
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
import uvicorn

from backend.app.core.config import settings
from backend.app.models.schemas import RootResponse, HealthResponse
from backend.app.routes.api import api_router
from backend.app.routes.health import health_check, readiness_check
from backend.app.services.embedding_service import embedding_service
from backend.app.rag.vector_store import vector_store_service
from backend.app.rag.embedder import initialize_default_embedder, EmbeddingModelManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown procedures."""
    startup_t0 = time.perf_counter()

    # 1. Execute crash-recovery scan on SQLite document registry
    embedding_service.startup_recovery_scan()

    # 2. Recover and initialize FAISS vector store to READY state
    try:
        vector_store_service.startup_recovery()
        logger.info("Vector store operational state: %s", vector_store_service.state)
    except Exception as err:
        logger.warning("Vector store startup recovery notice: %s", err)

    # 3. Initialize and warm up the dense embedding model once at startup
    try:
        await run_in_threadpool(initialize_default_embedder)
        manager = EmbeddingModelManager()
        timings = manager.timings
        logger.info(
            "Embedding service state: %s (load=%.1f ms, warmup=%.1f ms, total_startup=%.1f ms)",
            manager.status,
            timings.get("load_ms") or 0.0,
            timings.get("warmup_ms") or 0.0,
            (time.perf_counter() - startup_t0) * 1000.0,
        )
    except Exception as err:
        manager = EmbeddingModelManager()
        logger.error(
            "Embedding service initialization failed during startup (state=%s): %s",
            manager.status,
            err,
        )

    yield
    # Shutdown tasks (e.g. release resources)


def create_application() -> FastAPI:
    """Initialize and configure the FastAPI application."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="AI-Powered University Knowledge Assistant - Backend API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API v1 routes
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Top-level health & readiness endpoints for monitoring/load balancers
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["System"],
        summary="Service Health Check",
    )
    async def top_level_health() -> HealthResponse:
        return await health_check()

    @app.get(
        "/ready",
        response_model=HealthResponse,
        tags=["System"],
        summary="Service Readiness Check",
    )
    async def top_level_ready() -> HealthResponse:
        return await readiness_check()

    # Root informational endpoint
    @app.get(
        "/",
        response_model=RootResponse,
        tags=["System"],
        summary="Root Service Information",
    )
    async def root_info() -> RootResponse:
        return RootResponse(
            service=settings.PROJECT_NAME,
            version=settings.VERSION,
            status="online",
            docs_url="/docs",
            health_url="/health",
            api_v1_url=settings.API_V1_STR,
        )

    return app


app = create_application()

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
