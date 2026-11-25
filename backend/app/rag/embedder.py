"""Dense vector embedding generator, validation contracts, and model lifecycle manager."""

import os
import time
import logging
import threading
import hashlib
from typing import Dict, List, Optional, Union
import numpy as np
from fastapi import HTTPException, status

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_STATE_INITIALIZING = "INITIALIZING"
EMBEDDING_STATE_READY = "READY"
EMBEDDING_STATE_FAILED = "FAILED"


class ModelInitializationError(HTTPException):
    """Raised when the embedding model cannot be loaded or initialized."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Embedding model service unavailable: {detail}",
        )


class VectorValidationError(ValueError):
    """Raised when generated vector fails dimension, norm, or numeric sanity checks."""
    pass


class MockEmbeddingModel:
    """Fast, deterministic mock embedding model for isolated unit tests without network or PyTorch."""

    def __init__(self, dimension: int = 384, max_seq_length: int = 512, tokenizer=None):
        self.dimension = dimension
        self.max_seq_length = max_seq_length
        from backend.app.rag.chunker import SimpleWhitespaceTokenizer
        self.tokenizer = tokenizer or SimpleWhitespaceTokenizer()

    def encode(
        self,
        sentences: Union[str, List[str]],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        **kwargs,
    ) -> np.ndarray:
        if isinstance(sentences, str):
            single = True
            sentences = [sentences]
        else:
            single = False

        vectors = []
        for text in sentences:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            repeat_count = self.dimension // len(h) + 1
            raw_bytes = (h * repeat_count)[: self.dimension]
            raw = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0
            if np.all(raw == 0):
                raw[0] = 1.0
            if normalize_embeddings:
                norm = float(np.linalg.norm(raw))
                norm = norm if norm > 0 else 1.0
                raw = raw / norm
            vectors.append(raw.astype(np.float32))

        result = np.vstack(vectors)
        return result[0] if single else result


class EmbeddingModelManager:
    """Thread-safe singleton managing embedding model lifecycle, warmup, caching, and readiness."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EmbeddingModelManager, cls).__new__(cls)
                cls._instance._model = None
                cls._instance._model_name = None
                cls._instance._tokenizer = None
                cls._instance._state = EMBEDDING_STATE_INITIALIZING
                cls._instance._error = None
                cls._instance._load_time_ms = None
                cls._instance._warmup_time_ms = None
        return cls._instance

    @property
    def status(self) -> str:
        """Current embedding service readiness state: INITIALIZING, READY, or FAILED."""
        return self._state

    @property
    def error(self) -> Optional[str]:
        """Error message if initialization failed, otherwise None."""
        return self._error

    @property
    def timings(self) -> Dict[str, Optional[float]]:
        """Recorded model load and warmup timings in milliseconds."""
        return {
            "load_ms": self._load_time_ms,
            "warmup_ms": self._warmup_time_ms,
        }

    def _load_sentence_transformer(self, target_name: str):
        """Load SentenceTransformer, preferring local cache before checking remote HF Hub."""
        from sentence_transformers import SentenceTransformer

        cache_dir = settings.MODEL_CACHE_DIR or os.getenv("HF_HOME")
        try:
            return SentenceTransformer(target_name, cache_folder=cache_dir, local_files_only=True)
        except (OSError, FileNotFoundError, TypeError):
            # Fall back to standard download/resolution if not yet cached locally
            return SentenceTransformer(target_name, cache_folder=cache_dir)

    def get_model(self, model_name: Optional[str] = None, use_mock: bool = False):
        """Retrieve cached model instance with thread-safe singleton loading."""
        if use_mock:
            return MockEmbeddingModel(dimension=settings.EMBEDDING_DIMENSION)

        target_name = model_name or settings.EMBEDDING_MODEL_NAME

        # Lock-free fast path once initialized and ready
        if (
            self._model is not None
            and self._model_name == target_name
            and self._state == EMBEDDING_STATE_READY
        ):
            return self._model

        with self._lock:
            if (
                self._model is not None
                and self._model_name == target_name
                and self._state == EMBEDDING_STATE_READY
            ):
                return self._model

            # Do not retry loading on every request if startup/previous initialization failed
            if self._state == EMBEDDING_STATE_FAILED and self._model_name == target_name:
                raise ModelInitializationError(self._error or "Previous initialization failed.")

            self._state = EMBEDDING_STATE_INITIALIZING
            self._error = None
            t0 = time.perf_counter()
            try:
                model = self._load_sentence_transformer(target_name)
                self._load_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                self._model = model
                self._model_name = target_name
                self._state = EMBEDDING_STATE_READY
                return self._model
            except Exception as e:
                self._load_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                self._model = None
                self._model_name = target_name
                self._state = EMBEDDING_STATE_FAILED
                self._error = str(e)
                logger.exception("Failed to load embedding model '%s': %s", target_name, e)
                raise ModelInitializationError(f"Failed to load embedding model '{target_name}': {e}")

    def initialize_and_warmup(
        self,
        model_name: Optional[str] = None,
        force_retry: bool = False,
    ) -> Dict[str, Optional[float]]:
        """Load the embedding model and execute a warmup inference pass at application startup."""
        target_name = model_name or settings.EMBEDDING_MODEL_NAME

        with self._lock:
            if (
                not force_retry
                and self._state == EMBEDDING_STATE_READY
                and self._model is not None
                and self._model_name == target_name
            ):
                return self.timings

            if not force_retry and self._state == EMBEDDING_STATE_FAILED and self._model_name == target_name:
                raise ModelInitializationError(self._error or "Previous initialization failed.")

            self._state = EMBEDDING_STATE_INITIALIZING
            self._error = None
            self._model = None
            self._model_name = target_name

            t_load_start = time.perf_counter()
            try:
                model = self._load_sentence_transformer(target_name)
                self._load_time_ms = round((time.perf_counter() - t_load_start) * 1000.0, 2)
                self._model = model
                self._model_name = target_name

                # Warmup inference pass (tokenizer + model forward + L2 validation)
                t_warm_start = time.perf_counter()
                prefix = "query: " if "e5" in target_name.lower() else ""
                warm_vec = model.encode(
                    f"{prefix}warmup",
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                matrix = np.asarray(warm_vec, dtype=np.float32)
                if matrix.ndim == 1:
                    matrix = np.expand_dims(matrix, axis=0)
                validate_embedding_matrix(matrix, expected_dimension=settings.EMBEDDING_DIMENSION)
                self._warmup_time_ms = round((time.perf_counter() - t_warm_start) * 1000.0, 2)

                self._state = EMBEDDING_STATE_READY
                return self.timings
            except Exception as e:
                self._load_time_ms = round((time.perf_counter() - t_load_start) * 1000.0, 2)
                self._warmup_time_ms = None
                self._model = None
                self._state = EMBEDDING_STATE_FAILED
                self._error = str(e)
                logger.exception("Embedding model startup initialization/warmup failed for '%s': %s", target_name, e)
                if isinstance(e, ModelInitializationError):
                    raise
                raise ModelInitializationError(f"Failed to initialize embedding model '{target_name}': {e}")

    def reset_state(self) -> None:
        """Reset singleton state (intended solely for isolated unit tests)."""
        with self._lock:
            self._model = None
            self._model_name = None
            self._tokenizer = None
            self._state = EMBEDDING_STATE_INITIALIZING
            self._error = None
            self._load_time_ms = None
            self._warmup_time_ms = None


def validate_embedding_matrix(matrix: np.ndarray, expected_dimension: int = settings.EMBEDDING_DIMENSION) -> None:
    """Enforce strict vector validation contracts on a 2D embeddings matrix.

    Validates:
    - 2D array shape (N, dimension).
    - Float32 dtype.
    - Finite numeric values (no NaN, +Inf, -Inf).
    - L2 normalization (Euclidean unit norm ||v|| == 1.0 within 1e-4 tolerance).
    """
    if not isinstance(matrix, np.ndarray):
        raise VectorValidationError("Embeddings must be a NumPy array.")

    if matrix.ndim != 2:
        raise VectorValidationError(f"Expected 2D embedding matrix, got {matrix.ndim}D array.")

    num_vectors, dim = matrix.shape
    if dim != expected_dimension:
        raise VectorValidationError(f"Vector dimension mismatch: expected {expected_dimension}, got {dim}.")

    if matrix.dtype != np.float32:
        raise VectorValidationError(f"Invalid dtype: expected float32, got {matrix.dtype}.")

    if not np.isfinite(matrix).all():
        raise VectorValidationError("Embeddings matrix contains non-finite values (NaN or Inf).")

    norms = np.linalg.norm(matrix, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-4):
        invalid_idx = np.where(~np.isclose(norms, 1.0, atol=1e-4))[0]
        raise VectorValidationError(
            f"L2 normalization check failed: {len(invalid_idx)} vectors do not have unit norm."
        )


class DenseEmbedder:
    """Generates and validates dense vector representations for passages and queries."""

    def __init__(self, model_name: Optional[str] = None, use_mock: bool = False):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.use_mock = use_mock
        self.manager = EmbeddingModelManager()
        self.model = self.manager.get_model(self.model_name, use_mock=use_mock)

        # Determine prefix protocol
        if "e5" in self.model_name.lower():
            self.passage_prefix = "passage: "
            self.query_prefix = "query: "
        else:
            self.passage_prefix = ""
            self.query_prefix = ""

    def encode_passages(
        self,
        passages: List[str],
        batch_size: int = settings.EMBEDDING_BATCH_SIZE,
    ) -> np.ndarray:
        """Encode a batch of text passages into L2-normalized 384-dimensional dense vectors."""
        if not passages:
            return np.empty((0, settings.EMBEDDING_DIMENSION), dtype=np.float32)

        formatted_inputs = [f"{self.passage_prefix}{text.strip()}" for text in passages]

        if hasattr(self.model, "tokenizer") and hasattr(self.model, "max_seq_length"):
            max_len = self.model.max_seq_length
            for idx, text in enumerate(formatted_inputs):
                tok_len = len(self.model.tokenizer.encode(text, add_special_tokens=True))
                if tok_len > max_len:
                    raise VectorValidationError(
                        f"Chunk at index {idx} has {tok_len} tokens, exceeding model maximum capacity ({max_len}). "
                        "Input must be sub-chunked to prevent silent truncation."
                    )

        vectors = self.model.encode(
            formatted_inputs,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = np.expand_dims(matrix, axis=0)

        validate_embedding_matrix(matrix, expected_dimension=settings.EMBEDDING_DIMENSION)
        return matrix

    def embed_passages(
        self,
        passages: List[str],
        batch_size: int = settings.EMBEDDING_BATCH_SIZE,
    ) -> tuple[np.ndarray, dict]:
        """Encode passages and return the matrix along with validation summary statistics."""
        matrix = self.encode_passages(passages=passages, batch_size=batch_size)
        stats = {
            "count": int(matrix.shape[0]),
            "dimension": int(matrix.shape[1]),
            "dtype": str(matrix.dtype),
            "mean_norm": float(np.mean(np.linalg.norm(matrix, axis=1))) if matrix.shape[0] > 0 else 1.0,
        }
        return matrix, stats

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a user query into a single L2-normalized dense vector."""
        cleaned = query.strip()
        formatted = f"{self.query_prefix}{cleaned}"

        if hasattr(self.model, "tokenizer") and hasattr(self.model, "max_seq_length"):
            tok_len = len(self.model.tokenizer.encode(formatted, add_special_tokens=True))
            if tok_len > self.model.max_seq_length:
                raise VectorValidationError(
                    f"Query has {tok_len} tokens, exceeding model maximum capacity ({self.model.max_seq_length})."
                )

        vector = self.model.encode(
            formatted,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        vec = np.asarray(vector, dtype=np.float32)
        if vec.ndim == 1:
            vec = np.expand_dims(vec, axis=0)
        validate_embedding_matrix(vec, expected_dimension=settings.EMBEDDING_DIMENSION)
        return vec[0]


_default_embedder: Optional[DenseEmbedder] = None
_default_lock = threading.Lock()


def get_default_embedder() -> DenseEmbedder:
    """Retrieve or create the global default DenseEmbedder instance."""
    global _default_embedder
    if _default_embedder is not None and EmbeddingModelManager().status == EMBEDDING_STATE_READY:
        return _default_embedder

    with _default_lock:
        if _default_embedder is not None and EmbeddingModelManager().status == EMBEDDING_STATE_READY:
            return _default_embedder
        _default_embedder = DenseEmbedder()
        return _default_embedder


def initialize_default_embedder(model_name: Optional[str] = None, force_retry: bool = False) -> DenseEmbedder:
    """Initialize and warm up the global default DenseEmbedder during application startup."""
    global _default_embedder
    manager = EmbeddingModelManager()
    manager.initialize_and_warmup(model_name=model_name, force_retry=force_retry)
    with _default_lock:
        if _default_embedder is None or _default_embedder.model_name != (model_name or settings.EMBEDDING_MODEL_NAME):
            _default_embedder = DenseEmbedder(model_name=model_name)
        return _default_embedder


def reset_default_embedder() -> None:
    """Clear cached default embedder and model manager state (for isolated unit tests)."""
    global _default_embedder
    with _default_lock:
        _default_embedder = None
    EmbeddingModelManager().reset_state()
