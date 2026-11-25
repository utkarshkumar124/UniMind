"""API router for semantic retrieval, RAG question answering, and conversational chat."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.app.models.schemas import QueryRequest, QueryResponse
from backend.app.rag.embedder import (
    EmbeddingModelManager,
    EMBEDDING_STATE_FAILED,
    ModelInitializationError,
)
from backend.app.rag.generator import rag_pipeline
from backend.app.rag.retriever import RetrieverNotReadyError, RetrieverError

router = APIRouter(tags=["Retrieval & Chat"])


class ChatMessageRequest(BaseModel):
    """Payload sent by the frontend chat interface."""

    prompt: str = Field(..., min_length=1, description="User question or chat message")
    conversation_id: Optional[str] = Field(default=None, description="Optional conversation UUID")
    department: Optional[str] = Field(default=None, description="Department filter")
    category: Optional[str] = Field(default=None, description="Category filter")


class ChatReplyResponse(BaseModel):
    """Direct response contract expected by frontend ChatService."""

    content: str = Field(..., description="Generated answer text")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="List of source references")


def _ensure_embedding_service_available() -> None:
    """Fail fast with HTTP 503 if the global embedding service failed initialization."""
    if rag_pipeline.retriever._embedder is None:
        manager = EmbeddingModelManager()
        if manager.status == EMBEDDING_STATE_FAILED:
            raise ModelInitializationError(manager.error or "Startup initialization failed.")


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic Retrieval & Grounded RAG Question Answering",
)
async def query_knowledge_base(request: QueryRequest) -> QueryResponse:
    """Execute end-to-end RAG workflow without blocking the async event loop."""
    _ensure_embedding_service_available()
    try:
        response = await run_in_threadpool(
            rag_pipeline.answer_query,
            query=request.query,
            top_k=request.top_k,
            department=request.department,
            category=request.category,
            min_similarity=request.min_similarity,
        )
        return response
    except HTTPException:
        raise
    except RetrieverNotReadyError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Knowledge vector store is not ready: {err}",
        )
    except RetrieverError as err:
        if EmbeddingModelManager().status == EMBEDDING_STATE_FAILED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(err),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(err),
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while answering the query: {err}",
        )


@router.post(
    "/chat",
    response_model=ChatReplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Conversational Chat API for Frontend Integration",
)
async def chat_message(request: ChatMessageRequest) -> ChatReplyResponse:
    """Frontend-facing conversational endpoint matching React ChatService."""
    _ensure_embedding_service_available()
    try:
        rag_res = await run_in_threadpool(
            rag_pipeline.answer_query,
            query=request.prompt,
            top_k=4,
            department=request.department,
            category=request.category,
        )

        sources_payload = [
            {
                "n": s.n,
                "docId": s.doc_id,
                "docTitle": s.doc_title,
                "page": s.page,
                "quote": s.quote,
            }
            for s in rag_res.sources
        ]

        return ChatReplyResponse(
            content=rag_res.answer,
            sources=sources_payload,
        )
    except HTTPException:
        raise
    except RetrieverNotReadyError:
        return ChatReplyResponse(
            content=(
                "The university knowledge base is currently being initialized or updated. "
                "Please upload documents or retry in a few moments."
            ),
            sources=[],
        )
    except Exception as err:
        if EmbeddingModelManager().status == EMBEDDING_STATE_FAILED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Embedding service unavailable: {EmbeddingModelManager().error or err}",
            )
        return ChatReplyResponse(
            content=f"An unexpected error occurred while processing your question: {err}",
            sources=[],
        )
