"""FAISS vector store, generation bundle manager, and atomic persistence engine."""

import os
import sys
import json
import time
import uuid
import hashlib
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Dict, List, Optional, Tuple, Any, Generator
from contextlib import contextmanager

import faiss
import numpy as np

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Base exception for all vector store errors."""
    pass


class VectorStoreLockConflictError(VectorStoreError):
    """Raised when an operation cannot acquire the exclusive vector store lock."""
    pass


class VectorStoreCorruptionError(VectorStoreError):
    """Raised when an index or metadata file fails checksum or integrity checks."""
    pass


class VectorStoreNotReadyError(VectorStoreError):
    """Raised when query or search is requested but the vector store is not ready."""
    pass


class VectorStoreMutationError(VectorStoreError, TypeError):
    """Raised when an attempt is made to mutate a read-only vector store snapshot or index."""
    pass


def compute_file_sha256(path: Path) -> str:
    """Compute the SHA-256 hexadecimal hash of a file reading in chunks.

    Args:
        path: Path to the target file.

    Returns:
        Hexadecimal SHA-256 hash string.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def fsync_dir(path: Path, raise_on_failure: bool = False) -> bool:
    """Synchronize directory metadata changes to physical storage.

    On POSIX systems, opens the directory descriptor and calls os.fsync.
    Failures are explicitly logged and optionally raised.

    On Windows (nt), directory handle synchronization via os.fsync is not supported
    by the Win32 CRT (raises EINVAL). Windows relies on NTFS lazy metadata commits
    and transactional journal recovery for filesystem structural consistency.
    However, NTFS journaling does NOT guarantee immediate physical durability of
    directory entry modifications across sudden power loss without a volume-level flush.
    File payload durability is ensured separately via FlushFileBuffers on individual file
    descriptors prior to atomic directory rename.

    Args:
        path: Directory path to synchronize.
        raise_on_failure: If True, raises OSError on failure to halt the transaction.

    Returns:
        True if successfully synchronized or intentionally unsupported; False on logged failure.
    """
    if os.name == "nt":
        # Documented platform limitation: Windows CRT does not permit os.fsync
        # on directory handles (EINVAL). Relies on NTFS transactional metadata recovery.
        logger.debug("Directory fsync skipped on Windows (NTFS structural journal authoritative): %s", path)
        return True

    try:
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
            return True
        finally:
            os.close(fd)
    except OSError as err:
        logger.error("POSIX directory fsync failed on %s: %s", path, err, exc_info=True)
        if raise_on_failure:
            raise
        return False


class VectorStoreLock:
    """Cross-process and cross-thread advisory file lock for vector store mutations.

    Uses msvcrt.locking on Windows and fcntl.flock on POSIX. Reentrant within
    the same process/thread via threading.RLock and reference counting.
    """

    def __init__(self, lock_file: Path, timeout_seconds: float = 0.0):
        self.lock_file = lock_file
        self.timeout_seconds = timeout_seconds
        self._thread_lock = threading.RLock()
        self._count = 0
        self._fd: Optional[int] = None
        self._file_obj = None

    def acquire(self, timeout_seconds: Optional[float] = None) -> None:
        """Acquire the exclusive lock. Raises VectorStoreLockConflictError if held by another process."""
        self._thread_lock.acquire()
        if self._count > 0:
            self._count += 1
            return

        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        start_time = time.monotonic()

        while True:
            try:
                # Open or create lock file in binary append/read mode
                self._file_obj = open(self.lock_file, "a+b")
                self._fd = self._file_obj.fileno()

                if os.name == "nt":
                    import msvcrt
                    # Non-blocking lock on first byte
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    # Non-blocking exclusive lock
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                self._count = 1
                return

            except (OSError, IOError) as e:
                if self._file_obj:
                    try:
                        self._file_obj.close()
                    except Exception:
                        pass
                    self._file_obj = None
                    self._fd = None

                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    self._thread_lock.release()
                    raise VectorStoreLockConflictError(
                        f"Vector store mutation is currently locked by another process (error: {e}). "
                        f"Lock file: {self.lock_file}"
                    ) from e
                time.sleep(0.05)

    def release(self) -> None:
        """Release the exclusive lock."""
        if self._count <= 0:
            return

        self._count -= 1
        if self._count == 0:
            try:
                if self._file_obj and self._fd is not None:
                    if os.name == "nt":
                        import msvcrt
                        try:
                            msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                        except OSError:
                            pass
                    else:
                        import fcntl
                        try:
                            fcntl.flock(self._fd, fcntl.LOCK_UN)
                        except OSError:
                            pass
            finally:
                if self._file_obj:
                    try:
                        self._file_obj.close()
                    except Exception:
                        pass
                    self._file_obj = None
                    self._fd = None
                self._thread_lock.release()
        else:
            self._thread_lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class ReadOnlyFAISSIndex:
    """Read-only proxy wrapper around a FAISS IndexIDMap2 / IndexFlat.

    Exposes read-only inspection and vector search methods while strictly
    forbidding any mutating operations (add, add_with_ids, reset, remove_ids, train).
    """

    _MUTATING_METHODS = {
        "add",
        "add_with_ids",
        "reset",
        "remove_ids",
        "train",
        "merge_from",
    }

    def __init__(self, raw_index: Any):
        super().__setattr__("_raw_index", raw_index)
        super().__setattr__("_initialized", True)

    @property
    def ntotal(self) -> int:
        return self._raw_index.ntotal

    @property
    def d(self) -> int:
        return self._raw_index.d

    @property
    def is_trained(self) -> bool:
        return self._raw_index.is_trained

    @property
    def metric_type(self) -> int:
        return self._raw_index.metric_type

    def search(self, x: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """Execute vector similarity search delegating to the underlying index."""
        return self._raw_index.search(x, k)

    def reconstruct(self, key: int) -> np.ndarray:
        """Reconstruct vector by integer FAISS ID."""
        return self._raw_index.reconstruct(key)

    def reconstruct_n(self, n0: int, ni: int) -> np.ndarray:
        """Reconstruct a slice of vectors."""
        return self._raw_index.reconstruct_n(n0, ni)

    def __getattr__(self, name: str) -> Any:
        if name in self._MUTATING_METHODS:
            def _forbidden_method(*args, **kwargs):
                raise VectorStoreMutationError(
                    f"FAISS index in GenerationSnapshot is read-only; mutation method '{name}' is forbidden."
                )
            return _forbidden_method
        if name.startswith("_"):
            raise AttributeError(f"Private attribute '{name}' access denied on ReadOnlyFAISSIndex")
        return getattr(self._raw_index, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_initialized", False):
            raise AttributeError(f"ReadOnlyFAISSIndex is immutable; cannot reassign attribute '{name}'")
        super().__setattr__(name, value)

    def __repr__(self) -> str:
        return f"<ReadOnlyFAISSIndex d={self.d} ntotal={self.ntotal} metric_type={self.metric_type}>"


class GenerationSnapshot:
    """Immutable, point-in-time in-memory view of a FAISS index generation.

    Enforces strict immutability:
    - All metadata mappings are wrapped in read-only MappingProxyType views.
    - All document chunk ID lists are converted to immutable tuples.
    - All nested chunk metadata dictionaries are wrapped in read-only MappingProxyType views.
    - Attribute reassignment after initialization raises AttributeError.
    - The FAISS index is wrapped in a ReadOnlyFAISSIndex proxy blocking all mutations.
    - Reference counting for active readers is managed thread-safely via acquire() and release().
    """

    def __init__(
        self,
        generation_id: str,
        index: Any,
        metadata: dict,
        manifest: dict,
        directory: Path,
    ):
        self._initialized = False
        self.generation_id = generation_id
        self.index = index if isinstance(index, ReadOnlyFAISSIndex) else ReadOnlyFAISSIndex(index)
        self.directory = directory
        self.created_at = manifest.get("created_at", "")
        self.active_readers = 0
        self._ref_lock = threading.Lock()

        # Wrap mappings in read-only proxies
        int_to_chunk = {
            int(k): str(v) for k, v in metadata.get("int_to_chunk_id", {}).items()
        }
        chunk_to_int = {
            str(k): int(v) for k, v in metadata.get("chunk_id_to_int", {}).items()
        }
        doc_chunks = {
            str(k): tuple(str(cid) for cid in v)
            for k, v in metadata.get("doc_id_to_chunk_ids", {}).items()
        }
        frozen_chunk_meta = {
            str(k): MappingProxyType(dict(v)) if isinstance(v, dict) else v
            for k, v in metadata.get("chunk_metadata", {}).items()
        }

        self.int_to_chunk_id = MappingProxyType(int_to_chunk)
        self.chunk_id_to_int = MappingProxyType(chunk_to_int)
        self.doc_id_to_chunk_ids = MappingProxyType(doc_chunks)
        self.chunk_metadata = MappingProxyType(frozen_chunk_meta)
        self.next_id = int(metadata.get("next_id", 1))
        self.manifest = MappingProxyType(dict(manifest))

        self._initialized = True

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent external mutation of snapshot attributes after initialization."""
        if getattr(self, "_initialized", False):
            if name in ("active_readers",):
                super().__setattr__(name, value)
                return
            raise AttributeError(f"GenerationSnapshot is immutable; cannot reassign '{name}'")
        super().__setattr__(name, value)

    def acquire(self) -> None:
        """Increment active reader reference count."""
        with self._ref_lock:
            self.active_readers += 1

    def release(self) -> None:
        """Decrement active reader reference count."""
        with self._ref_lock:
            self.active_readers = max(0, self.active_readers - 1)

    def get_chunk_id(self, faiss_id: int) -> Optional[str]:
        """Safely lookup chunk ID from FAISS integer ID."""
        return self.int_to_chunk_id.get(faiss_id)

    def get_faiss_id(self, chunk_id: str) -> Optional[int]:
        """Safely lookup FAISS integer ID from chunk ID."""
        return self.chunk_id_to_int.get(chunk_id)

    def get_chunk_metadata(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Safely retrieve a copy of metadata for a specific chunk."""
        meta = self.chunk_metadata.get(chunk_id)
        return dict(meta) if meta is not None else None

    def get_doc_chunk_ids(self, doc_id: str) -> Tuple[str, ...]:
        """Safely retrieve tuple of chunk IDs belonging to a document."""
        return self.doc_id_to_chunk_ids.get(doc_id, ())

    def search(self, query_vectors: np.ndarray, top_k: int) -> Tuple[np.ndarray, np.ndarray]:
        """Execute read-only similarity search on the snapshot's FAISS index."""
        return self.index.search(query_vectors, top_k)

    @property
    def total_vectors(self) -> int:
        return self.index.ntotal if self.index else 0

    @property
    def total_chunks(self) -> int:
        return len(self.chunk_metadata)

    @property
    def total_documents(self) -> int:
        return len(self.doc_id_to_chunk_ids)


class VectorStoreService:
    """Singleton service managing FAISS generation bundles, atomic persistence, and recovery."""

    def __init__(
        self,
        index_dir: Optional[str] = None,
        retention_keep_count: int = 3,
        retention_grace_period_seconds: float = 900.0,
    ):
        self.index_dir = Path(index_dir or settings.VECTOR_STORE_DIR)
        self.retention_keep_count = retention_keep_count
        self.retention_grace_period_seconds = retention_grace_period_seconds
        self.generations_dir = self.index_dir / "generations"
        self.pointer_file = self.index_dir / "current_generation.json"
        self.lock_file = self.index_dir / ".vector_store.lock"
        self.quarantine_dir = self.index_dir / "quarantine"

        self._thread_lock = threading.RLock()
        self._snapshot_lock = threading.Lock()
        self._current_snapshot: Optional[GenerationSnapshot] = None
        self._state: str = "STARTING"
        self._last_error: Optional[str] = None
        self._process_lock = VectorStoreLock(self.lock_file)

    @property
    def is_ready(self) -> bool:
        """Check if vector store is ready to serve queries."""
        with self._snapshot_lock:
            return self._state == "READY" and self._current_snapshot is not None

    @property
    def state(self) -> str:
        """Current operational lifecycle state."""
        with self._snapshot_lock:
            return self._state

    @property
    def active_generation_id(self) -> Optional[str]:
        """ID of currently active generation bundle."""
        with self._snapshot_lock:
            return self._current_snapshot.generation_id if self._current_snapshot else None

    @property
    def total_vectors(self) -> int:
        """Total vectors indexed in current generation."""
        with self._snapshot_lock:
            return self._current_snapshot.total_vectors if self._current_snapshot else 0

    @property
    def total_chunks(self) -> int:
        """Total chunks cataloged in current generation."""
        with self._snapshot_lock:
            return self._current_snapshot.total_chunks if self._current_snapshot else 0

    @property
    def total_documents(self) -> int:
        """Total unique documents in current generation."""
        with self._snapshot_lock:
            return self._current_snapshot.total_documents if self._current_snapshot else 0

    @property
    def current_snapshot(self) -> Optional[GenerationSnapshot]:
        """Direct access to current snapshot (internal use)."""
        with self._snapshot_lock:
            return self._current_snapshot

    @contextmanager
    def acquire_snapshot(self) -> Generator[GenerationSnapshot, None, None]:
        """Reader acquisition context manager.

        Provides isolated, lock-free access to the active generation snapshot.
        Prevents generation pruning while queries are active.
        """
        with self._snapshot_lock:
            if self._state != "READY" or self._current_snapshot is None:
                raise VectorStoreNotReadyError(
                    f"Vector store is not ready (state={self._state}, error={self._last_error})"
                )
            snapshot = self._current_snapshot
            snapshot.acquire()

        try:
            yield snapshot
        finally:
            snapshot.release()

    def _get_process_lock(self, timeout_seconds: float = 0.0) -> VectorStoreLock:
        return self._process_lock

    def create_empty_index(self, dimension: int = settings.EMBEDDING_DIMENSION) -> faiss.IndexIDMap2:
        """Construct a new empty FAISS IndexIDMap2 wrapping IndexFlatIP."""
        flat_index = faiss.IndexFlatIP(dimension)
        return faiss.IndexIDMap2(flat_index)

    def commit_generation_bundle(
        self,
        index: faiss.IndexIDMap2,
        metadata: dict,
        parent_generation_id: Optional[str] = None,
        tx_id: Optional[str] = None,
    ) -> GenerationSnapshot:
        """Atomically persist an immutable generation bundle and update the pointer.

        Args:
            index: In-memory FAISS IndexIDMap2.
            metadata: Metadata dictionary containing mapping structures.
            parent_generation_id: Optional previous generation ID.
            tx_id: Optional transaction UUID.

        Returns:
            Newly committed GenerationSnapshot.
        """
        tx_id = tx_id or str(uuid.uuid4())
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        generation_id = f"gen_{timestamp_str}_{tx_id[:8]}"

        self.generations_dir.mkdir(parents=True, exist_ok=True)
        gen_dir = self.generations_dir / generation_id
        gen_dir.mkdir(parents=True, exist_ok=False)

        index_file = gen_dir / "index.faiss"
        meta_file = gen_dir / "metadata.json"
        manifest_file = gen_dir / "manifest.json"

        with self._thread_lock, self._get_process_lock():
            try:
                # 1. Serialize FAISS index
                raw_index = index._raw_index if isinstance(index, ReadOnlyFAISSIndex) else index
                faiss.write_index(raw_index, str(index_file))
                with open(index_file, "r+b") as f:
                    f.flush()
                    os.fsync(f.fileno())

                # 2. Serialize Metadata JSON
                # Ensure int_to_chunk_id keys are serialized as strings for valid JSON
                serialized_metadata = {
                    "int_to_chunk_id": {str(k): v for k, v in metadata.get("int_to_chunk_id", {}).items()},
                    "chunk_id_to_int": {k: int(v) for k, v in metadata.get("chunk_id_to_int", {}).items()},
                    "doc_id_to_chunk_ids": metadata.get("doc_id_to_chunk_ids", {}),
                    "chunk_metadata": metadata.get("chunk_metadata", {}),
                    "next_id": int(metadata.get("next_id", 1)),
                }
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(serialized_metadata, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # 3. Compute Checksums
                index_sha256 = compute_file_sha256(index_file)
                meta_sha256 = compute_file_sha256(meta_file)

                # 4. Write Generation Manifest
                manifest_data = {
                    "generation_id": generation_id,
                    "tx_id": tx_id,
                    "parent_generation_id": parent_generation_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "total_vectors": raw_index.ntotal,
                    "total_chunks": len(serialized_metadata["chunk_metadata"]),
                    "total_documents": len(serialized_metadata["doc_id_to_chunk_ids"]),
                    "dimension": settings.EMBEDDING_DIMENSION,
                    "metric": "INNER_PRODUCT",
                    "index_sha256": index_sha256,
                    "metadata_sha256": meta_sha256,
                    "state": "COMMITTED",
                }
                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(manifest_data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # Sync generation directory descriptor on POSIX
                fsync_dir(gen_dir, raise_on_failure=True)

                manifest_sha256 = compute_file_sha256(manifest_file)

                # 5. Staged Pointer File
                staged_pointer = self.index_dir / f"current_generation.json.staged_{tx_id}"
                pointer_data = {
                    "active_generation_id": generation_id,
                    "tx_id": tx_id,
                    "switched_at": datetime.now(timezone.utc).isoformat(),
                    "manifest_sha256": manifest_sha256,
                }
                with open(staged_pointer, "w", encoding="utf-8") as f:
                    json.dump(pointer_data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # 6. Strictly validate new generation bundle from disk before pointer switch
                new_snapshot = self.load_generation(generation_id)

                # 7. Single-Pointer Atomic Swap (Same Filesystem)
                os.replace(staged_pointer, self.pointer_file)

                # The authoritative on-disk pointer has transitioned to new_snapshot.
                # Synchronize in-memory snapshot immediately so the running service cannot
                # silently retain an old snapshot while disk points to the new generation.
                with self._snapshot_lock:
                    self._current_snapshot = new_snapshot
                    self._state = "READY"
                    self._last_error = None

                # 8. Physical directory synchronization
                try:
                    fsync_dir(self.index_dir, raise_on_failure=True)
                except Exception as fsync_err:
                    logger.error(
                        "Directory fsync failed after atomic pointer replacement for generation %s: %s",
                        generation_id,
                        fsync_err,
                        exc_info=True,
                    )
                    with self._snapshot_lock:
                        self._last_error = f"Directory fsync failed after pointer switch: {fsync_err}"
                    raise VectorStoreError(
                        f"Generation {generation_id} pointer replaced on disk, but directory fsync failed: {fsync_err}"
                    ) from fsync_err

                logger.info(
                    "Committed vector store generation %s (vectors=%d, docs=%d)",
                    generation_id,
                    new_snapshot.total_vectors,
                    new_snapshot.total_documents,
                )

            except Exception as e:
                logger.error("Failed to commit generation bundle %s: %s", generation_id, e, exc_info=True)
                raise

        # 9. Asynchronous background pruning of older generations OUTSIDE the commit lock
        try:
            self.prune_historical_generations(
                keep_count=self.retention_keep_count,
                grace_period_seconds=self.retention_grace_period_seconds,
            )
        except Exception as e:
            logger.warning("Generation pruning encountered error: %s", e)

        return new_snapshot

    def load_generation(self, generation_id: str) -> GenerationSnapshot:
        """Load and strictly validate a specific generation bundle from disk.

        Performs comprehensive integrity validation:
        1. File bundle completeness (index.faiss, metadata.json, manifest.json).
        2. Manifest status and SHA-256 cryptographic checksums for index and metadata.
        3. Index dimension validation against configured EMBEDDING_DIMENSION.
        4. Manifest count validation against actual index and metadata contents.
        5. Bidirectional ID mapping consistency and uniqueness (int_to_chunk_id <-> chunk_id_to_int).
        6. Metadata references and internal coherence (chunk catalog, document partitions, provenance).

        Args:
            generation_id: Bundle identifier.

        Returns:
            Validated GenerationSnapshot.

        Raises:
            VectorStoreCorruptionError: If checksums, counts, dimensions, or mappings fail validation.
        """
        gen_dir = self.generations_dir / generation_id
        if not gen_dir.is_dir():
            raise VectorStoreCorruptionError(f"Generation directory does not exist: {gen_dir}")

        index_file = gen_dir / "index.faiss"
        meta_file = gen_dir / "metadata.json"
        manifest_file = gen_dir / "manifest.json"

        if not (index_file.exists() and meta_file.exists() and manifest_file.exists()):
            raise VectorStoreCorruptionError(
                f"Generation bundle {generation_id} is incomplete. Missing one or more required files."
            )

        # 1. Parse Manifest
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception as e:
            raise VectorStoreCorruptionError(f"Cannot parse manifest for {generation_id}: {e}") from e

        if manifest_data.get("state") != "COMMITTED":
            raise VectorStoreCorruptionError(
                f"Generation {generation_id} has state '{manifest_data.get('state')}', expected COMMITTED."
            )

        # 2. Checksum Verification
        actual_index_sha256 = compute_file_sha256(index_file)
        if actual_index_sha256 != manifest_data.get("index_sha256"):
            raise VectorStoreCorruptionError(
                f"Index checksum mismatch for {generation_id}: "
                f"expected {manifest_data.get('index_sha256')}, got {actual_index_sha256}"
            )

        actual_meta_sha256 = compute_file_sha256(meta_file)
        if actual_meta_sha256 != manifest_data.get("metadata_sha256"):
            raise VectorStoreCorruptionError(
                f"Metadata checksum mismatch for {generation_id}: "
                f"expected {manifest_data.get('metadata_sha256')}, got {actual_meta_sha256}"
            )

        # 3. Read FAISS index and validate dimension
        try:
            index = faiss.read_index(str(index_file))
        except Exception as e:
            raise VectorStoreCorruptionError(f"FAISS failed to read index for {generation_id}: {e}") from e

        if index.d != settings.EMBEDDING_DIMENSION:
            raise VectorStoreCorruptionError(
                f"Index dimension mismatch for {generation_id}: "
                f"index has dimension {index.d}, configured is {settings.EMBEDDING_DIMENSION}"
            )

        manifest_dim = manifest_data.get("dimension")
        if manifest_dim is not None and manifest_dim != settings.EMBEDDING_DIMENSION:
            raise VectorStoreCorruptionError(
                f"Manifest dimension mismatch for {generation_id}: "
                f"manifest declared {manifest_dim}, configured is {settings.EMBEDDING_DIMENSION}"
            )

        # 4. Read Metadata
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            raise VectorStoreCorruptionError(f"Cannot parse metadata for {generation_id}: {e}") from e

        # 5. Manifest count validation against index and metadata
        if index.ntotal != manifest_data.get("total_vectors"):
            raise VectorStoreCorruptionError(
                f"Vector count mismatch for {generation_id}: "
                f"index has {index.ntotal}, manifest declared {manifest_data.get('total_vectors')}"
            )

        chunk_meta = metadata.get("chunk_metadata", {})
        if len(chunk_meta) != manifest_data.get("total_chunks"):
            raise VectorStoreCorruptionError(
                f"Chunk count mismatch for {generation_id}: "
                f"metadata has {len(chunk_meta)} chunks, manifest declared {manifest_data.get('total_chunks')}"
            )

        doc_to_chunks = metadata.get("doc_id_to_chunk_ids", {})
        if len(doc_to_chunks) != manifest_data.get("total_documents"):
            raise VectorStoreCorruptionError(
                f"Document count mismatch for {generation_id}: "
                f"metadata has {len(doc_to_chunks)} documents, manifest declared {manifest_data.get('total_documents')}"
            )

        # 6. ID mapping consistency and uniqueness
        int_to_chunk = {int(k): str(v) for k, v in metadata.get("int_to_chunk_id", {}).items()}
        chunk_to_int = {str(k): int(v) for k, v in metadata.get("chunk_id_to_int", {}).items()}

        if len(int_to_chunk) != index.ntotal:
            raise VectorStoreCorruptionError(
                f"int_to_chunk_id mapping size ({len(int_to_chunk)}) does not match index.ntotal ({index.ntotal}) for {generation_id}"
            )
        if len(chunk_to_int) != index.ntotal:
            raise VectorStoreCorruptionError(
                f"chunk_id_to_int mapping size ({len(chunk_to_int)}) does not match index.ntotal ({index.ntotal}) for {generation_id}"
            )

        # Uniqueness of mapping values
        if len(set(int_to_chunk.values())) != len(int_to_chunk):
            raise VectorStoreCorruptionError(
                f"Duplicate chunk IDs detected in int_to_chunk_id mapping for {generation_id}"
            )
        if len(set(chunk_to_int.values())) != len(chunk_to_int):
            raise VectorStoreCorruptionError(
                f"Duplicate FAISS integer IDs detected in chunk_id_to_int mapping for {generation_id}"
            )

        # Bijective 1-to-1 equivalence
        for fid, cid in int_to_chunk.items():
            if chunk_to_int.get(cid) != fid:
                raise VectorStoreCorruptionError(
                    f"Inconsistent bidirectional ID mapping for chunk '{cid}' in {generation_id}: "
                    f"int_to_chunk_id has {fid}, chunk_id_to_int has {chunk_to_int.get(cid)}"
                )
        for cid, fid in chunk_to_int.items():
            if int_to_chunk.get(fid) != cid:
                raise VectorStoreCorruptionError(
                    f"Inconsistent bidirectional ID mapping for FAISS ID {fid} in {generation_id}: "
                    f"chunk_id_to_int has '{cid}', int_to_chunk_id has '{int_to_chunk.get(fid)}'"
                )

        # Boundary check for next_id
        next_id = int(metadata.get("next_id", 1))
        if int_to_chunk:
            max_faiss_id = max(int_to_chunk.keys())
            if next_id <= max_faiss_id:
                raise VectorStoreCorruptionError(
                    f"Metadata next_id ({next_id}) must be strictly greater than maximum allocated FAISS ID ({max_faiss_id}) in {generation_id}"
                )

        # 7. Metadata references and internal coherence
        chunk_meta_keys = set(chunk_meta.keys())
        chunk_to_int_keys = set(chunk_to_int.keys())
        if chunk_meta_keys != chunk_to_int_keys:
            raise VectorStoreCorruptionError(
                f"Chunk catalog mismatch in {generation_id}: chunk_metadata keys do not match indexed chunks "
                f"(diff: {chunk_meta_keys ^ chunk_to_int_keys})"
            )

        # Document partition coherence: all chunk IDs in doc_id_to_chunk_ids must exactly partition chunk_metadata
        aggregated_doc_chunks = []
        for doc_id, cids in doc_to_chunks.items():
            if not isinstance(cids, list):
                raise VectorStoreCorruptionError(
                    f"doc_id_to_chunk_ids entry for '{doc_id}' in {generation_id} must be a list"
                )
            for cid in cids:
                aggregated_doc_chunks.append(str(cid))

        if len(aggregated_doc_chunks) != len(set(aggregated_doc_chunks)):
            raise VectorStoreCorruptionError(
                f"Duplicate chunk IDs found across document entries in {generation_id} (non-disjoint partitions)"
            )
        if set(aggregated_doc_chunks) != chunk_meta_keys:
            raise VectorStoreCorruptionError(
                f"Document chunk mappings do not span the catalog in {generation_id} "
                f"(diff: {set(aggregated_doc_chunks) ^ chunk_meta_keys})"
            )

        # Chunk metadata provenance integrity
        for cid, cinfo in chunk_meta.items():
            if not isinstance(cinfo, dict):
                raise VectorStoreCorruptionError(
                    f"Chunk metadata payload for '{cid}' in {generation_id} is not a dictionary"
                )
            doc_id = cinfo.get("doc_id")
            if not doc_id or doc_id not in doc_to_chunks:
                raise VectorStoreCorruptionError(
                    f"Chunk '{cid}' in {generation_id} references missing or uncataloged doc_id: '{doc_id}'"
                )
            if cid not in doc_to_chunks[doc_id]:
                raise VectorStoreCorruptionError(
                    f"Chunk '{cid}' in {generation_id} references doc_id '{doc_id}', but is not in doc_id_to_chunk_ids['{doc_id}']"
                )
            if cinfo.get("chunk_id") and cinfo.get("chunk_id") != cid:
                raise VectorStoreCorruptionError(
                    f"Chunk metadata self-identifier mismatch for '{cid}' in {generation_id}: payload declared '{cinfo.get('chunk_id')}'"
                )

        snapshot = GenerationSnapshot(
            generation_id=generation_id,
            index=index,
            metadata=metadata,
            manifest=manifest_data,
            directory=gen_dir,
        )
        return snapshot

    def load_active_generation(self) -> GenerationSnapshot:
        """Load and activate the generation referenced by current_generation.json."""
        if not self.pointer_file.exists():
            raise VectorStoreCorruptionError(f"Pointer file does not exist: {self.pointer_file}")

        try:
            with open(self.pointer_file, "r", encoding="utf-8") as f:
                pointer_data = json.load(f)
        except Exception as e:
            raise VectorStoreCorruptionError(f"Failed to read current_generation.json: {e}") from e

        active_gen_id = pointer_data.get("active_generation_id")
        if not active_gen_id:
            raise VectorStoreCorruptionError("current_generation.json missing active_generation_id")

        snapshot = self.load_generation(active_gen_id)

        # Verify pointer manifest hash if present
        expected_manifest_hash = pointer_data.get("manifest_sha256")
        if expected_manifest_hash:
            actual_manifest_hash = compute_file_sha256(snapshot.directory / "manifest.json")
            if actual_manifest_hash != expected_manifest_hash:
                raise VectorStoreCorruptionError(
                    f"Pointer manifest hash mismatch for {active_gen_id}: "
                    f"expected {expected_manifest_hash}, got {actual_manifest_hash}"
                )

        with self._snapshot_lock:
            self._current_snapshot = snapshot
            self._state = "READY"
            self._last_error = None

        return snapshot

    def create_empty_generation(self, parent_generation_id: Optional[str] = None) -> GenerationSnapshot:
        """Construct and commit a clean initial empty generation bundle."""
        index = self.create_empty_index()
        metadata = {
            "int_to_chunk_id": {},
            "chunk_id_to_int": {},
            "doc_id_to_chunk_ids": {},
            "chunk_metadata": {},
            "next_id": 1,
        }
        return self.commit_generation_bundle(
            index=index,
            metadata=metadata,
            parent_generation_id=parent_generation_id,
        )

    def startup_recovery(self) -> GenerationSnapshot:
        """Run startup recovery scan for generation bundles.

        - Cleans orphaned staged pointer files.
        - Loads active generation.
        - Falls back to parent generation if active is corrupted.
        - Quarantines irrecoverably corrupted generations and marks REBUILD_REQUIRED.
        - Creates clean empty generation if vector store is newly initialized.
        """
        with self._thread_lock, self._get_process_lock():
            self._state = "RECOVERING"
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self.generations_dir.mkdir(parents=True, exist_ok=True)

            # 1. Clean orphaned staged pointer files
            for p in self.index_dir.glob("current_generation.json.staged_*"):
                try:
                    p.unlink()
                    logger.info("Cleaned orphaned staged pointer file: %s", p)
                except OSError as e:
                    logger.warning("Could not unlink staged pointer %s: %s", p, e)

            # 2. Check if current_generation.json exists
            if self.pointer_file.exists():
                try:
                    snapshot = self.load_active_generation()
                    logger.info("Successfully loaded active generation on startup: %s", snapshot.generation_id)
                    return snapshot
                except VectorStoreCorruptionError as err:
                    logger.error("Active generation is corrupted: %s. Attempting rollback...", err)

                    # Attempt rollback to parent generation
                    try:
                        with open(self.pointer_file, "r", encoding="utf-8") as f:
                            pointer_data = json.load(f)
                        corrupted_id = pointer_data.get("active_generation_id")
                    except Exception:
                        corrupted_id = None

                    parent_id = None
                    if corrupted_id:
                        corrupted_manifest = self.generations_dir / corrupted_id / "manifest.json"
                        if corrupted_manifest.exists():
                            try:
                                with open(corrupted_manifest, "r", encoding="utf-8") as f:
                                    parent_id = json.load(f).get("parent_generation_id")
                            except Exception:
                                pass

                    if parent_id:
                        try:
                            logger.info("Attempting rollback to parent generation: %s", parent_id)
                            parent_snapshot = self.load_generation(parent_id)

                            # Re-point current_generation.json to valid parent
                            tx_id = str(uuid.uuid4())
                            staged_pointer = self.index_dir / f"current_generation.json.staged_{tx_id}"
                            manifest_sha256 = compute_file_sha256(parent_snapshot.directory / "manifest.json")
                            pointer_data = {
                                "active_generation_id": parent_id,
                                "tx_id": tx_id,
                                "switched_at": datetime.now(timezone.utc).isoformat(),
                                "manifest_sha256": manifest_sha256,
                            }
                            with open(staged_pointer, "w", encoding="utf-8") as f:
                                json.dump(pointer_data, f, indent=2)
                                f.flush()
                                os.fsync(f.fileno())

                            os.replace(staged_pointer, self.pointer_file)
                            fsync_dir(self.index_dir)

                            with self._snapshot_lock:
                                self._current_snapshot = parent_snapshot
                                self._state = "READY"
                                self._last_error = None

                            logger.warning(
                                "Successfully rolled back to parent generation %s after corruption.", parent_id
                            )
                            return parent_snapshot

                        except Exception as parent_err:
                            logger.error("Parent generation rollback failed: %s", parent_err)

                    # Both active and parent corrupted/unavailable -> Quarantine
                    self._quarantine_corrupted_store(corrupted_id)
                    with self._snapshot_lock:
                        self._state = "REBUILD_REQUIRED"
                        self._last_error = f"Active generation corrupted and rollback unavailable: {err}"
                    raise

            # 3. If no pointer exists, scan for latest committed generation
            committed_generations = []
            for g_dir in self.generations_dir.iterdir():
                if g_dir.is_dir() and (g_dir / "manifest.json").exists():
                    try:
                        with open(g_dir / "manifest.json", "r", encoding="utf-8") as f:
                            m = json.load(f)
                            if m.get("state") == "COMMITTED":
                                committed_generations.append((m.get("created_at", ""), g_dir.name))
                    except Exception:
                        pass

            if committed_generations:
                committed_generations.sort(reverse=True)
                latest_gen_id = committed_generations[0][1]
                logger.info("Found un-pointed committed generation %s; adopting as active", latest_gen_id)
                try:
                    snapshot = self.load_generation(latest_gen_id)
                    tx_id = str(uuid.uuid4())
                    staged_pointer = self.index_dir / f"current_generation.json.staged_{tx_id}"
                    manifest_sha256 = compute_file_sha256(snapshot.directory / "manifest.json")
                    pointer_data = {
                        "active_generation_id": latest_gen_id,
                        "tx_id": tx_id,
                        "switched_at": datetime.now(timezone.utc).isoformat(),
                        "manifest_sha256": manifest_sha256,
                    }
                    with open(staged_pointer, "w", encoding="utf-8") as f:
                        json.dump(pointer_data, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(staged_pointer, self.pointer_file)
                    fsync_dir(self.index_dir)

                    with self._snapshot_lock:
                        self._current_snapshot = snapshot
                        self._state = "READY"
                        self._last_error = None
                    return snapshot
                except Exception as e:
                    logger.warning("Failed to adopt un-pointed generation %s: %s", latest_gen_id, e)

            # 4. If brand new or empty, initialize generation 0
            logger.info("Initializing fresh empty generation bundle")
            return self.create_empty_generation()

    def _quarantine_corrupted_store(self, corrupted_generation_id: Optional[str]) -> None:
        """Isolate corrupted generations to prevent data loss or crash loops."""
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target_quarantine = self.quarantine_dir / f"quarantine_{timestamp}"
        target_quarantine.mkdir(parents=True, exist_ok=True)

        if self.pointer_file.exists():
            try:
                os.replace(self.pointer_file, target_quarantine / "current_generation.json")
            except OSError:
                pass

        if corrupted_generation_id:
            src_gen = self.generations_dir / corrupted_generation_id
            if src_gen.exists():
                try:
                    os.replace(src_gen, target_quarantine / corrupted_generation_id)
                except OSError:
                    pass

        logger.error("Corrupted vector store files moved to quarantine: %s", target_quarantine)

    def prune_historical_generations(
        self,
        keep_count: int = 3,
        grace_period_seconds: float = 900.0,
        lock_timeout_seconds: float = 5.0,
    ) -> List[str]:
        """Prune older generation bundles outside the retention window.

        Safety & concurrency guarantees:
        - Acquires local _thread_lock and cross-process advisory lock to avoid
          concurrent pruning, commit, or recovery race conditions.
        - Deferrable: If another process holds the lock, pruning defers cleanly
          rather than blocking or raising.
        - Authoritatively reads current_generation.json from disk to protect active generation.
        - Protects the parent generation of the active generation for rollback safety.
        - Protects any generation currently referenced by an active reader in this process.
        - Preserves at least `keep_count` most recent generations regardless of age.
        - Enforces `grace_period_seconds` minimum age before unlinking.
        - Gracefully handles filesystem sharing violations on Windows (open file descriptors).

        Args:
            keep_count: Number of recent generations to retain (default 3).
            grace_period_seconds: Minimum age in seconds before a generation can be unlinked.
            lock_timeout_seconds: Timeout in seconds for acquiring the cross-process lock.

        Returns:
            List of pruned generation IDs.
        """
        # Strict lock ordering: _thread_lock -> _get_process_lock
        with self._thread_lock:
            try:
                proc_lock = self._get_process_lock()
                proc_lock.acquire(timeout_seconds=lock_timeout_seconds)
            except VectorStoreLockConflictError:
                logger.info("Deferred historical generation pruning: vector store lock held by another process")
                return []

            try:
                if not self.generations_dir.exists():
                    return []

                # 1. Authoritative active generation and its parent from disk pointer
                active_id = None
                parent_id = None
                if self.pointer_file.exists():
                    try:
                        with open(self.pointer_file, "r", encoding="utf-8") as f:
                            active_id = json.load(f).get("active_generation_id")
                    except Exception:
                        active_id = self.active_generation_id

                if active_id:
                    active_manifest = self.generations_dir / active_id / "manifest.json"
                    if active_manifest.exists():
                        try:
                            with open(active_manifest, "r", encoding="utf-8") as f:
                                parent_id = json.load(f).get("parent_generation_id")
                        except Exception:
                            pass

                # 2. Protected generation set
                protected_generations = set()
                if active_id:
                    protected_generations.add(active_id)
                if parent_id:
                    protected_generations.add(parent_id)

                with self._snapshot_lock:
                    if self._current_snapshot and self._current_snapshot.active_readers > 0:
                        protected_generations.add(self._current_snapshot.generation_id)

                now = time.time()
                generations = []

                for d in self.generations_dir.iterdir():
                    if d.is_dir() and d.name.startswith("gen_"):
                        manifest_path = d / "manifest.json"
                        created_at_ts = d.stat().st_mtime
                        if manifest_path.exists():
                            try:
                                with open(manifest_path, "r", encoding="utf-8") as f:
                                    m = json.load(f)
                                    iso_str = m.get("created_at")
                                    if iso_str:
                                        created_at_ts = datetime.fromisoformat(iso_str).timestamp()
                            except Exception:
                                pass
                        generations.append((created_at_ts, d.name, d))

                # Sort descending: newest first
                generations.sort(key=lambda x: x[0], reverse=True)

                pruned = []
                # Keep the newest keep_count generations
                candidates_to_prune = generations[keep_count:]

                for ts, gen_name, gen_path in candidates_to_prune:
                    if gen_name in protected_generations:
                        continue

                    age_seconds = now - ts
                    if age_seconds < grace_period_seconds:
                        continue

                    try:
                        # Clean all files in directory
                        for f in gen_path.iterdir():
                            try:
                                f.unlink()
                            except (OSError, PermissionError) as e:
                                logger.debug("Prune file unlink deferred: %s (%s)", f, e)
                        gen_path.rmdir()
                        pruned.append(gen_name)
                        logger.info("Pruned retired generation bundle: %s", gen_name)
                    except (OSError, PermissionError) as e:
                        logger.debug("Prune directory removal deferred: %s (%s)", gen_path, e)

                return pruned
            finally:
                proc_lock.release()

    def get_status(self) -> dict:
        """Return diagnostic metrics of vector store."""
        with self._snapshot_lock:
            snap = self._current_snapshot
            index_bytes = 0
            meta_bytes = 0
            if snap and snap.directory:
                idx_p = snap.directory / "index.faiss"
                if idx_p.exists():
                    index_bytes = idx_p.stat().st_size
                meta_p = snap.directory / "metadata.json"
                if meta_p.exists():
                    meta_bytes = meta_p.stat().st_size

            return {
                "status": self._state,
                "active_generation_id": snap.generation_id if snap else None,
                "total_vectors": snap.total_vectors if snap else 0,
                "total_chunks": snap.total_chunks if snap else 0,
                "total_documents": snap.total_documents if snap else 0,
                "dimension": settings.EMBEDDING_DIMENSION,
                "metric": "INNER_PRODUCT",
                "index_file_bytes": index_bytes,
                "metadata_file_bytes": meta_bytes,
                "checksum_sha256": snap.manifest.get("index_sha256") if snap else None,
                "last_switched_at": snap.manifest.get("created_at") if snap else None,
                "last_error": self._last_error,
            }

    def clear_index(self) -> dict:
        """Reset vector store to an empty generation bundle.

        Non-destructive: authoritative documents, SQLite DB, and processed chunks remain intact.
        """
        with self._thread_lock, self._get_process_lock():
            parent_id = self.active_generation_id
            snap = self.create_empty_generation(parent_generation_id=parent_id)
            return {
                "status": "CLEARED",
                "message": "Vector store reset to empty generation bundle.",
                "generation_id": snap.generation_id,
                "cleared_at": datetime.now(timezone.utc).isoformat(),
            }


# Global vector store service singleton
vector_store_service = VectorStoreService()
