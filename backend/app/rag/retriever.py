"""Semantic vector retrieval engine integrating FAISS vector store with dense embeddings."""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import numpy as np

from backend.app.core.config import settings
from backend.app.rag.embedder import DenseEmbedder, get_default_embedder
from backend.app.rag.vector_store import (
    VectorStoreService,
    vector_store_service,
    VectorStoreNotReadyError,
    VectorStoreError,
)

logger = logging.getLogger(__name__)


class RetrieverError(Exception):
    """Base exception for retrieval engine errors."""
    pass


class RetrieverNotReadyError(RetrieverError):
    """Raised when the vector store is not ready to serve queries."""
    pass


@dataclass(frozen=True)
class RetrievedChunk:
    """Individual retrieved document chunk with semantic score and provenance."""

    chunk_id: str
    doc_id: str
    text: str
    score: float
    page_start: int
    page_end: int
    department: Optional[str] = None
    category: Optional[str] = None
    filename: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    """Structured response container for a retrieval query execution."""

    query: str
    chunks: List[RetrievedChunk]
    total_found: int
    latency_ms: float
    generation_id: Optional[str] = None


class SemanticRetriever:
    """Semantic retrieval engine querying FAISS vector store using dense representations."""

    def __init__(
        self,
        vector_store: Optional[VectorStoreService] = None,
        embedder: Optional[DenseEmbedder] = None,
        default_top_k: int = 5,
        default_min_similarity: Optional[float] = None,
    ):
        self.vector_store = vector_store or vector_store_service
        self._embedder = embedder
        self.default_top_k = default_top_k
        self.default_min_similarity = default_min_similarity

    @property
    def embedder(self) -> DenseEmbedder:
        """Lazily initialize or return the dense embedder."""
        if self._embedder is None:
            self._embedder = get_default_embedder()
        return self._embedder

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        department: Optional[str] = None,
        category: Optional[str] = None,
        min_similarity: Optional[float] = None,
    ) -> RetrievalResult:
        """Retrieve the most semantically relevant chunks for a user query.

        Args:
            query: Natural language query string.
            top_k: Maximum number of chunks to return (default 5).
            department: Optional department metadata filter.
            category: Optional category metadata filter.
            min_similarity: Optional minimum cosine similarity threshold in [-1.0, 1.0].

        Returns:
            RetrievalResult containing ranked chunks, score metrics, and latency.

        Raises:
            ValueError: If query is empty or top_k <= 0.
            RetrieverNotReadyError: If vector store is uninitialized or unready.
        """
        start_time = time.perf_counter()

        # 1. Input validation
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query string must be non-empty text.")

        k = top_k if top_k is not None else self.default_top_k
        if k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {k}.")

        threshold = min_similarity if min_similarity is not None else self.default_min_similarity

        # 2. Acquire point-in-time vector store snapshot
        try:
            with self.vector_store.acquire_snapshot() as snapshot:
                # 3. Handle empty vector index cleanly
                if snapshot.total_vectors == 0:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return RetrievalResult(
                        query=query.strip(),
                        chunks=[],
                        total_found=0,
                        latency_ms=elapsed_ms,
                        generation_id=snapshot.generation_id,
                    )

                # 4. Generate L2-normalized dense query vector
                try:
                    query_vec = self.embedder.encode_query(query)
                except Exception as err:
                    logger.error("Query embedding failed for '%s': %s", query, err)
                    raise RetrieverError(f"Failed to generate query embedding: {err}") from err

                # Ensure query vector is shape (1, dimension) float32
                query_matrix = np.asarray(query_vec, dtype=np.float32)
                if query_matrix.ndim == 1:
                    query_matrix = np.expand_dims(query_matrix, axis=0)

                # 5. Over-fetch if metadata filters or threshold are present
                has_filters = bool(department or category or threshold is not None)
                search_k = min(snapshot.total_vectors, max(k * 4, 20) if has_filters else k)

                # 6. FAISS similarity search (Inner Product on normalized vectors = Cosine Similarity)
                distances, indices = snapshot.search(query_matrix, top_k=search_k)

                # 7. Filter, rank, and reconstruct structured chunks
                retrieved_chunks: List[RetrievedChunk] = []

                for score_val, faiss_id_val in zip(distances[0], indices[0]):
                    faiss_id = int(faiss_id_val)
                    if faiss_id < 0:
                        continue  # Unfilled FAISS sentinel

                    score = float(score_val)

                    # Similarity threshold filter
                    if threshold is not None and score < threshold:
                        continue

                    chunk_id = snapshot.get_chunk_id(faiss_id)
                    if not chunk_id:
                        continue

                    meta = snapshot.get_chunk_metadata(chunk_id) or {}

                    # Metadata filtering (case-insensitive for safety)
                    if department and str(meta.get("department", "")).lower() != department.strip().lower():
                        continue

                    if category and str(meta.get("category", "")).lower() != category.strip().lower():
                        continue

                    chunk = RetrievedChunk(
                        chunk_id=chunk_id,
                        doc_id=str(meta.get("doc_id", "")),
                        text=str(meta.get("text", "")),
                        score=score,
                        page_start=int(meta.get("page_start", 1)),
                        page_end=int(meta.get("page_end", meta.get("page_start", 1))),
                        department=meta.get("department"),
                        category=meta.get("category"),
                        filename=meta.get("filename"),
                        metadata=meta,
                    )
                    retrieved_chunks.append(chunk)

                    if len(retrieved_chunks) >= k:
                        break

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                return RetrievalResult(
                    query=query.strip(),
                    chunks=retrieved_chunks,
                    total_found=len(retrieved_chunks),
                    latency_ms=elapsed_ms,
                    generation_id=snapshot.generation_id,
                )

        except VectorStoreNotReadyError as err:
            logger.warning("Retriever called while vector store not ready: %s", err)
            raise RetrieverNotReadyError(f"Vector store is not ready for retrieval: {err}") from err
        except (ValueError, RetrieverError):
            raise
        except Exception as err:
            logger.error("Retrieval execution failed: %s", err)
            raise RetrieverError(f"Retrieval execution failed: {err}") from err


# Default singleton instance
retriever = SemanticRetriever()
