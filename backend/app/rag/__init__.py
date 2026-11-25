"""Retrieval-Augmented Generation (RAG) module and document processing engine."""

from backend.app.rag.cleaner import clean_text, extract_snippet
from backend.app.rag.parser import parse_pdf_document, PDFParsingError
from backend.app.rag.chunker import DocumentChunker, calculate_effective_token_budget
from backend.app.rag.embedder import DenseEmbedder, get_default_embedder, MockEmbeddingModel
from backend.app.rag.vector_store import (
    VectorStoreService,
    GenerationSnapshot,
    ReadOnlyFAISSIndex,
    VectorStoreError,
    VectorStoreMutationError,
    VectorStoreLockConflictError,
    VectorStoreCorruptionError,
    VectorStoreNotReadyError,
    vector_store_service,
)
from backend.app.rag.retriever import (
    SemanticRetriever,
    RetrievedChunk,
    RetrievalResult,
    RetrieverError,
    RetrieverNotReadyError,
    retriever,
)

__all__ = [
    "clean_text",
    "extract_snippet",
    "parse_pdf_document",
    "PDFParsingError",
    "DocumentChunker",
    "calculate_effective_token_budget",
    "DenseEmbedder",
    "get_default_embedder",
    "MockEmbeddingModel",
    "VectorStoreService",
    "GenerationSnapshot",
    "ReadOnlyFAISSIndex",
    "VectorStoreError",
    "VectorStoreMutationError",
    "VectorStoreLockConflictError",
    "VectorStoreCorruptionError",
    "VectorStoreNotReadyError",
    "vector_store_service",
    "SemanticRetriever",
    "RetrievedChunk",
    "RetrievalResult",
    "RetrieverError",
    "RetrieverNotReadyError",
    "retriever",
]
