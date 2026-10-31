"""UniMind FastAPI Application Entry Point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.app.core.config import settings
from backend.app.models.schemas import RootResponse, HealthResponse
from backend.app.routes.api import api_router
from backend.app.routes.health import health_check
from backend.app.services.embedding_service import embedding_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown procedures."""
    # Execute crash-recovery scan before accepting incoming requests
    embedding_service.startup_recovery_scan()
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

    # Top-level health check endpoint for monitoring/load balancers
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Root Health Check",
    )
    async def root_health_check() -> HealthResponse:
        return await health_check()

    # Root welcome/status endpoint
    @app.get(
        "/",
        response_model=RootResponse,
        tags=["System"],
        summary="Service Index",
    )
    async def root() -> RootResponse:
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

