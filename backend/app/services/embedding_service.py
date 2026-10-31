"""Embedding Service: Orchestrates chunking, vector generation, manifest-driven persistence,
authoritative SQLite CAS concurrency locking, and crash-safe startup recovery.
"""

import os
import json
import time
import uuid
import hashlib
import sqlite3
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from backend.app.core.config import settings
from backend.app.models.schemas import DocumentChunk, BlockReference, DocumentProcessResponse
from backend.app.rag.chunker import DocumentChunker
from backend.app.rag.embedder import DenseEmbedder, get_default_embedder
from backend.app.services.document_service import document_service


class ConcurrencyConflictError(Exception):
    """Raised when a document is locked by another concurrent processing transaction."""
    pass


class DocumentNotFoundError(Exception):
    """Raised when the target document does not exist in the registry."""
    pass


class InvalidDocumentStateError(Exception):
    """Raised when the document cannot be processed due to invalid state or empty content."""
    pass


def compute_file_sha256(filepath: str) -> str:
    """Compute the SHA-256 checksum of a file on disk."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class EmbeddingService:
    """Manages document chunking, embedding generation, manifest-backed atomic storage,
    and crash-safe transactional recovery.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        chunker: Optional[DocumentChunker] = None,
        embedder: Optional[DenseEmbedder] = None,
    ):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self.processed_dir = settings.DATA_PROCESSED_DIR
        self.raw_dir = settings.DATA_RAW_DIR
        self.chunker = chunker or DocumentChunker()
        self._embedder = embedder

    @property
    def embedder(self) -> DenseEmbedder:
        """Lazily initialize or return the dense embedder."""
        if self._embedder is None:
            self._embedder = get_default_embedder()
        return self._embedder

    def _get_connection(self) -> sqlite3.Connection:
        """Create a SQLite connection with busy timeout and foreign keys enabled."""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # -------------------------------------------------------------------------
    # Concurrency Lock & CAS State Transition
    # -------------------------------------------------------------------------

    def acquire_processing_lock(self, doc_id: str, tx_id: str, force: bool = False) -> Dict[str, Any]:
        """Atomically acquire the SQLite processing lock for a document.

        Args:
            doc_id: UUID of the document.
            tx_id: Generated transaction ID for this processing run.
            force: If True, allows reprocessing an already INDEXED document.

        Returns:
            The document database record.

        Raises:
            DocumentNotFoundError: If doc_id does not exist.
            ConcurrencyConflictError: If another process is currently processing or deleting the doc.
            InvalidDocumentStateError: If document is empty or in an invalid state.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE;")
            try:
                cursor = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
                record = cursor.fetchone()
                if not record:
                    conn.execute("ROLLBACK;")
                    raise DocumentNotFoundError(f"Document with doc_id '{doc_id}' not found.")

                doc_dict = dict(record)
                current_status = doc_dict["status"]

                if current_status == "PROCESSING_EMBEDDINGS":
                    conn.execute("ROLLBACK;")
                    staged_tx = doc_dict.get("staged_tx_id", "unknown")
                    raise ConcurrencyConflictError(
                        f"Document '{doc_id}' is currently being processed by transaction '{staged_tx}'."
                    )

                if current_status == "DELETING":
                    conn.execute("ROLLBACK;")
                    raise ConcurrencyConflictError(f"Document '{doc_id}' is currently being deleted.")

                if doc_dict.get("is_empty", 0) == 1:
                    conn.execute("ROLLBACK;")
                    raise InvalidDocumentStateError(f"Document '{doc_id}' is empty and cannot be embedded.")

                # Allowed source statuses for embedding
                allowed_statuses = ["PROCESSED", "FAILED"]
                if force:
                    allowed_statuses.append("INDEXED")

                if current_status not in allowed_statuses:
                    conn.execute("ROLLBACK;")
                    raise ConcurrencyConflictError(
                        f"Document '{doc_id}' is in status '{current_status}'. "
                        f"Allowed statuses for processing are: {allowed_statuses}."
                    )

                # Atomic CAS update within BEGIN IMMEDIATE
                placeholders = ",".join("?" for _ in allowed_statuses)
                params = ["PROCESSING_EMBEDDINGS", tx_id, now_iso, doc_id] + allowed_statuses
                update_cursor = conn.execute(
                    f"""
                    UPDATE documents
                    SET status = ?, staged_tx_id = ?, updated_at = ?
                    WHERE doc_id = ? AND status IN ({placeholders});
                    """,
                    params,
                )

                if update_cursor.rowcount == 0:
                    conn.execute("ROLLBACK;")
                    raise ConcurrencyConflictError(
                        f"Failed to acquire processing lock for document '{doc_id}' due to concurrent state change."
                    )

                conn.execute("COMMIT;")
                return doc_dict
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise

    # -------------------------------------------------------------------------
    # Core Processing Pipeline
    # -------------------------------------------------------------------------

    def process_document(self, doc_id: str, force: bool = False) -> DocumentProcessResponse:
        """Execute end-to-end chunking and embedding generation under transactional manifest control.

        Args:
            doc_id: UUID of document to process.
            force: Whether to reprocess already INDEXED documents.

        Returns:
            DocumentProcessResponse schema.
        """
        start_time = time.perf_counter()
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"

        # 1. Acquire SQLite CAS Lock
        doc_record = self.acquire_processing_lock(doc_id=doc_id, tx_id=tx_id, force=force)

        # File paths
        processed_json_path = os.path.join(self.processed_dir, f"{doc_id}.json")
        active_chunks_path = os.path.join(self.processed_dir, f"{doc_id}_chunks.json")
        active_emb_path = os.path.join(self.processed_dir, f"{doc_id}_embeddings.npy")
        manifest_path = os.path.join(self.processed_dir, f"{doc_id}_tx_{tx_id}.manifest.json")

        staged_chunks_path = f"{active_chunks_path}.staged_{tx_id}"
        staged_emb_path = f"{active_emb_path}.staged_{tx_id}"
        backup_chunks_path = f"{active_chunks_path}.backup_{tx_id}"
        backup_emb_path = f"{active_emb_path}.backup_{tx_id}"

        # 2. Record initial manifest
        chunks_existed = os.path.exists(active_chunks_path)
        emb_existed = os.path.exists(active_emb_path)

        manifest: Dict[str, Any] = {
            "tx_id": tx_id,
            "doc_id": doc_id,
            "stage": "STAGING",
            "db_committed": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "active_files_pre_existing": {
                "chunks_file": chunks_existed,
                "embeddings_file": emb_existed,
            },
            "files": {
                "chunks": {
                    "active_path": active_chunks_path,
                    "staged_path": staged_chunks_path,
                    "backup_path": backup_chunks_path,
                    "expected_sha256": None,
                    "size_bytes": 0,
                    "rotated": False,
                },
                "embeddings": {
                    "active_path": active_emb_path,
                    "staged_path": staged_emb_path,
                    "backup_path": backup_emb_path,
                    "expected_sha256": None,
                    "size_bytes": 0,
                    "rotated": False,
                },
            },
        }
        self._write_manifest(manifest_path, manifest)

        try:
            # 3. Load processed document data
            if not os.path.exists(processed_json_path):
                raise InvalidDocumentStateError(f"Processed JSON file not found at '{processed_json_path}'.")

            with open(processed_json_path, "r", encoding="utf-8") as f:
                doc_data = json.load(f)

            pages = doc_data.get("pages", [])
            if not pages:
                raise InvalidDocumentStateError(f"Document '{doc_id}' contains 0 pages.")

            # 4. Generate Semantic Chunks
            chunks = self.chunker.chunk_document(
                doc_id=doc_id,
                filename=doc_data.get("filename", doc_record["filename"]),
                department=doc_data.get("department", doc_record["department"]),
                category=doc_data.get("category", doc_record["category"]),
                file_hash=doc_data.get("file_hash", doc_record["file_hash"]),
                pages=pages,
            )

            if not chunks:
                raise InvalidDocumentStateError(f"Document '{doc_id}' produced 0 chunks after text extraction.")

            # 5. Generate Dense Embeddings
            texts_to_embed = [c.text for c in chunks]
            embeddings, val_stats = self.embedder.embed_passages(texts_to_embed)

            # Assign row offsets
            for idx, c in enumerate(chunks):
                c.embedding_offset = idx

            # 6. Stage files to disk with flush and fsync
            # 6a. Staged chunks JSON
            chunks_payload = [c.model_dump() for c in chunks]
            with open(staged_chunks_path, "w", encoding="utf-8") as f:
                json.dump(chunks_payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            chunks_sha = compute_file_sha256(staged_chunks_path)
            manifest["files"]["chunks"]["expected_sha256"] = chunks_sha
            manifest["files"]["chunks"]["size_bytes"] = os.path.getsize(staged_chunks_path)

            # 6b. Staged embeddings NumPy
            with open(staged_emb_path, "wb") as f:
                np.save(f, embeddings)
                f.flush()
                os.fsync(f.fileno())

            emb_sha = compute_file_sha256(staged_emb_path)
            manifest["files"]["embeddings"]["expected_sha256"] = emb_sha
            manifest["files"]["embeddings"]["size_bytes"] = os.path.getsize(staged_emb_path)

            # Update manifest: Entering ROTATING stage
            manifest["stage"] = "ROTATING"
            self._write_manifest(manifest_path, manifest)

            # 7. Rotate files: active -> backup, staged -> active
            # 7a. Chunks rotation
            if chunks_existed and os.path.exists(active_chunks_path):
                os.replace(active_chunks_path, backup_chunks_path)
            os.replace(staged_chunks_path, active_chunks_path)
            manifest["files"]["chunks"]["rotated"] = True
            self._write_manifest(manifest_path, manifest)

            # 7b. Embeddings rotation
            if emb_existed and os.path.exists(active_emb_path):
                os.replace(active_emb_path, backup_emb_path)
            os.replace(staged_emb_path, active_emb_path)
            manifest["files"]["embeddings"]["rotated"] = True
            manifest["stage"] = "ROTATED"
            self._write_manifest(manifest_path, manifest)

            # 8. Atomic SQLite commit with BEGIN IMMEDIATE
            now_iso = datetime.now(timezone.utc).isoformat()
            with self._get_connection() as conn:
                conn.isolation_level = None
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    # First delete any existing chunks for this document
                    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

                    # Insert newly generated chunks
                    chunk_rows = [
                        (
                            c.chunk_id,
                            c.doc_id,
                            c.page_start,
                            c.page_end,
                            c.chunk_index,
                            c.token_count,
                            c.char_count,
                            c.text,
                            c.embedding_offset,
                            c.created_at,
                        )
                        for c in chunks
                    ]
                    conn.executemany(
                        """
                        INSERT INTO chunks (
                            chunk_id, doc_id, page_start, page_end, chunk_index,
                            token_count, char_count, text, embedding_offset, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        chunk_rows,
                    )

                    # Update document status and set active_tx_id
                    update_cursor = conn.execute(
                        """
                        UPDATE documents SET
                            status = 'INDEXED',
                            active_tx_id = ?,
                            staged_tx_id = NULL,
                            total_chunks = ?,
                            updated_at = ?
                        WHERE doc_id = ? AND staged_tx_id = ?;
                        """,
                        (tx_id, len(chunks), now_iso, doc_id, tx_id),
                    )

                    if update_cursor.rowcount == 0:
                        conn.execute("ROLLBACK;")
                        raise ConcurrencyConflictError(
                            f"Database commit failed: lock for transaction '{tx_id}' was superseded."
                        )

                    conn.execute("COMMIT;")
                except Exception:
                    try:
                        conn.execute("ROLLBACK;")
                    except Exception:
                        pass
                    raise

            # Update manifest: COMMITTED
            manifest["stage"] = "COMMITTED"
            manifest["db_committed"] = True
            self._write_manifest(manifest_path, manifest)

            # 9. Finalizing: clean up backups and manifest
            self._safe_remove(backup_chunks_path)
            self._safe_remove(backup_emb_path)
            self._safe_remove(manifest_path)

            elapsed = time.perf_counter() - start_time
            return DocumentProcessResponse(
                doc_id=doc_id,
                status="INDEXED",
                total_chunks=len(chunks),
                model_name=self.embedder.model_name,
                vector_dimension=int(embeddings.shape[1]),
                embedding_file=os.path.basename(active_emb_path),
                chunks_file=os.path.basename(active_chunks_path),
                processing_time_seconds=round(elapsed, 4),
                processed_at=now_iso,
            )

        except Exception as e:
            # On failure before DB commit, rollback files and mark FAILED
            self._rollback_transaction(
                doc_id=doc_id,
                tx_id=tx_id,
                manifest=manifest,
                manifest_path=manifest_path,
                error_message=str(e),
            )
            raise e

    # -------------------------------------------------------------------------
    # Transaction Rollback & Manifest Helpers
    # -------------------------------------------------------------------------

    def _rollback_transaction(
        self,
        doc_id: str,
        tx_id: str,
        manifest: Dict[str, Any],
        manifest_path: str,
        error_message: str,
    ) -> None:
        """Rollback disk files and revert SQLite document status using manifest and verified file inspection."""
        chunks_info = manifest["files"]["chunks"]
        emb_info = manifest["files"]["embeddings"]
        active_pre = manifest.get("active_files_pre_existing", {})

        # Clean staged files unconditionally
        self._safe_remove(chunks_info.get("staged_path"))
        self._safe_remove(emb_info.get("staged_path"))

        # 1. Rollback Chunks File
        if os.path.exists(chunks_info["backup_path"]):
            os.replace(chunks_info["backup_path"], chunks_info["active_path"])
        elif not active_pre.get("chunks_file", False):
            # No pre-existing file; if active was created from this tx, remove it
            if os.path.exists(chunks_info["active_path"]):
                active_sha = compute_file_sha256(chunks_info["active_path"])
                if active_sha == chunks_info.get("expected_sha256"):
                    self._safe_remove(chunks_info["active_path"])
        else:
            # Pre-existing file existed, backup missing: check if active is the new file
            if os.path.exists(chunks_info["active_path"]):
                active_sha = compute_file_sha256(chunks_info["active_path"])
                if active_sha == chunks_info.get("expected_sha256"):
                    # New file in active position, but old backup missing -> data corrupted!
                    self._quarantine_transaction(doc_id=doc_id, tx_id=tx_id, manifest_path=manifest_path)
                    return

        # 2. Rollback Embeddings File
        if os.path.exists(emb_info["backup_path"]):
            os.replace(emb_info["backup_path"], emb_info["active_path"])
        elif not active_pre.get("embeddings_file", False):
            if os.path.exists(emb_info["active_path"]):
                active_sha = compute_file_sha256(emb_info["active_path"])
                if active_sha == emb_info.get("expected_sha256"):
                    self._safe_remove(emb_info["active_path"])
        else:
            if os.path.exists(emb_info["active_path"]):
                active_sha = compute_file_sha256(emb_info["active_path"])
                if active_sha == emb_info.get("expected_sha256"):
                    self._quarantine_transaction(doc_id=doc_id, tx_id=tx_id, manifest_path=manifest_path)
                    return

        # Revert SQLite document status safely
        revert_status = "PROCESSED" if (active_pre.get("chunks_file") and active_pre.get("embeddings_file")) else "FAILED"
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.isolation_level = None
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    """
                    UPDATE documents SET
                        status = ?,
                        staged_tx_id = NULL,
                        error_message = ?,
                        updated_at = ?
                    WHERE doc_id = ? AND (staged_tx_id = ? OR staged_tx_id IS NULL);
                    """,
                    (revert_status, error_message, now_iso, doc_id, tx_id),
                )
                conn.execute("COMMIT;")
        except Exception:
            pass

        # Remove manifest after successful rollback
        self._safe_remove(manifest_path)

    def _write_manifest(self, filepath: str, data: Dict[str, Any]) -> None:
        """Atomically persist transaction manifest with flush and fsync."""
        temp_path = f"{filepath}.tmp_{uuid.uuid4().hex[:8]}"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)

    def _safe_remove(self, filepath: Optional[str]) -> None:
        """Safely delete a file if it exists, ignoring errors."""
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    # -------------------------------------------------------------------------
    # Crash Recovery Scanner
    # -------------------------------------------------------------------------

    def startup_recovery_scan(self) -> Dict[str, Any]:
        """Scan data/processed for interrupted transaction manifests and resolve crashes.

        Handles Crash Points 1 through 8:
        - Committed: ensure active files are finalized, verify checksums, delete backups and manifest.
        - Uncommitted: restore backups if active was disturbed, purge staged, reset DB state.
        - Inconsistent: quarantine files to prevent silent data loss.

        Returns:
            Dictionary with counts of resolved, rolled_back, and quarantined transactions.
        """
        results = {"resolved": 0, "rolled_back": 0, "quarantined": 0, "manifests_found": 0}
        if not os.path.exists(self.processed_dir):
            return results

        manifest_files = [f for f in os.listdir(self.processed_dir) if f.endswith(".manifest.json")]
        results["manifests_found"] = len(manifest_files)

        for m_file in manifest_files:
            m_path = os.path.join(self.processed_dir, m_file)
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                # Corrupted manifest -> quarantine
                self._quarantine_file(m_path)
                results["quarantined"] += 1
                continue

            tx_id = manifest.get("tx_id")
            doc_id = manifest.get("doc_id")
            stage = manifest.get("stage")
            db_committed = manifest.get("db_committed", False)

            # Check database state
            doc_record = None
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
                    row = cur.fetchone()
                    if row:
                        doc_record = dict(row)
            except Exception:
                pass

            is_db_indexed = (
                doc_record is not None
                and doc_record.get("status") == "INDEXED"
                and doc_record.get("active_tx_id") == tx_id
            )

            # Case A: Database is committed
            if db_committed or is_db_indexed:
                chunks_info = manifest["files"]["chunks"]
                emb_info = manifest["files"]["embeddings"]

                # If active files are missing, restore from staged or backup
                if not os.path.exists(chunks_info["active_path"]):
                    if os.path.exists(chunks_info["staged_path"]):
                        os.replace(chunks_info["staged_path"], chunks_info["active_path"])
                    elif os.path.exists(chunks_info["backup_path"]):
                        os.replace(chunks_info["backup_path"], chunks_info["active_path"])

                if not os.path.exists(emb_info["active_path"]):
                    if os.path.exists(emb_info["staged_path"]):
                        os.replace(emb_info["staged_path"], emb_info["active_path"])
                    elif os.path.exists(emb_info["backup_path"]):
                        os.replace(emb_info["backup_path"], emb_info["active_path"])

                # Verify checksums of active files against manifest expected_sha256
                chunks_ok = (
                    os.path.exists(chunks_info["active_path"])
                    and (
                        chunks_info.get("expected_sha256") is None
                        or compute_file_sha256(chunks_info["active_path"]) == chunks_info["expected_sha256"]
                    )
                )
                emb_ok = (
                    os.path.exists(emb_info["active_path"])
                    and (
                        emb_info.get("expected_sha256") is None
                        or compute_file_sha256(emb_info["active_path"]) == emb_info["expected_sha256"]
                    )
                )

                if chunks_ok and emb_ok:
                    self._safe_remove(chunks_info.get("backup_path"))
                    self._safe_remove(chunks_info.get("staged_path"))
                    self._safe_remove(emb_info.get("backup_path"))
                    self._safe_remove(emb_info.get("staged_path"))
                    self._safe_remove(m_path)
                    results["resolved"] += 1
                else:
                    self._quarantine_transaction(doc_id=doc_id, tx_id=tx_id, manifest_path=m_path)
                    results["quarantined"] += 1

            # Case B: Uncommitted -> Rollback
            else:
                chunks_info = manifest["files"]["chunks"]
                emb_info = manifest["files"]["embeddings"]
                active_pre = manifest.get("active_files_pre_existing", {})

                # Check if backup was lost after rotation
                chunks_rotated = chunks_info.get("rotated", False) or (
                    os.path.exists(chunks_info["active_path"])
                    and chunks_info.get("expected_sha256") is not None
                    and compute_file_sha256(chunks_info["active_path"]) == chunks_info["expected_sha256"]
                )
                emb_rotated = emb_info.get("rotated", False) or (
                    os.path.exists(emb_info["active_path"])
                    and emb_info.get("expected_sha256") is not None
                    and compute_file_sha256(emb_info["active_path"]) == emb_info["expected_sha256"]
                )

                chunks_corrupted = (
                    active_pre.get("chunks_file", False)
                    and chunks_rotated
                    and not os.path.exists(chunks_info["backup_path"])
                )
                emb_corrupted = (
                    active_pre.get("embeddings_file", False)
                    and emb_rotated
                    and not os.path.exists(emb_info["backup_path"])
                )

                if chunks_corrupted or emb_corrupted:
                    self._quarantine_transaction(doc_id=doc_id, tx_id=tx_id, manifest_path=m_path)
                    results["quarantined"] += 1
                else:
                    self._rollback_transaction(
                        doc_id=doc_id,
                        tx_id=tx_id,
                        manifest=manifest,
                        manifest_path=m_path,
                        error_message=f"Interrupted transaction {tx_id} recovered during startup.",
                    )
                    results["rolled_back"] += 1

        # Also scan and resolve any lingering documents with 'DELETING' status
        self._recover_stuck_deletions()

        return results

    def _recover_stuck_deletions(self) -> None:
        """Scan for documents stuck in 'DELETING' status and complete deletion."""
        try:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT doc_id FROM documents WHERE status = 'DELETING'")
                stuck = [row["doc_id"] for row in cur.fetchall()]
            for doc_id in stuck:
                self.delete_document_recoverable(doc_id)
        except Exception:
            pass

    def _quarantine_file(self, filepath: str) -> None:
        """Move an unrecoverable corrupted file to quarantine."""
        quarantine_path = f"{filepath}.quarantine_{uuid.uuid4().hex[:6]}"
        try:
            os.replace(filepath, quarantine_path)
        except OSError:
            pass

    def _quarantine_transaction(self, doc_id: str, tx_id: str, manifest_path: Optional[str] = None) -> None:
        """Safely quarantine all transaction artifacts into a dedicated folder without data destruction."""
        quarantine_dir = os.path.join(self.processed_dir, f"{doc_id}.quarantine_{tx_id}")
        os.makedirs(quarantine_dir, exist_ok=True)
        if os.path.exists(self.processed_dir):
            for fname in os.listdir(self.processed_dir):
                if tx_id in fname:
                    src = os.path.join(self.processed_dir, fname)
                    dst = os.path.join(quarantine_dir, fname)
                    try:
                        os.replace(src, dst)
                    except OSError:
                        pass
        if manifest_path and os.path.exists(manifest_path):
            dst = os.path.join(quarantine_dir, os.path.basename(manifest_path))
            try:
                os.replace(manifest_path, dst)
            except OSError:
                pass

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.isolation_level = None
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    """
                    UPDATE documents SET
                        status = 'MANUAL_RECOVERY_REQUIRED',
                        error_message = ?,
                        updated_at = ?
                    WHERE doc_id = ?;
                    """,
                    (f"Corrupted or ambiguous state encountered during recovery of transaction {tx_id}", now_iso, doc_id),
                )
                conn.execute("COMMIT;")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Recoverable Document Deletion
    # -------------------------------------------------------------------------

    def delete_document_recoverable(self, doc_id: str) -> bool:
        """Execute safe, recoverable deletion of a document, its disk artifacts,
        active vectors, staged/backup files, and database records.

        Args:
            doc_id: UUID of document to delete.

        Returns:
            True if deleted, False if document did not exist.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE;")
            try:
                cur = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
                record = cur.fetchone()
                if not record:
                    conn.execute("ROLLBACK;")
                    return False

                # Set status to DELETING
                conn.execute(
                    "UPDATE documents SET status = 'DELETING', updated_at = ? WHERE doc_id = ?",
                    (now_iso, doc_id),
                )
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise

        # Delete all disk artifacts associated with this doc_id
        patterns = [
            os.path.join(self.raw_dir, f"{doc_id}.pdf"),
            os.path.join(self.processed_dir, f"{doc_id}.json"),
            os.path.join(self.processed_dir, f"{doc_id}_chunks.json"),
            os.path.join(self.processed_dir, f"{doc_id}_embeddings.npy"),
        ]
        for p in patterns:
            self._safe_remove(p)

        # Clean any staged, backup, or manifest files for this doc_id
        if os.path.exists(self.processed_dir):
            for fname in os.listdir(self.processed_dir):
                if fname.startswith(f"{doc_id}_tx_") or fname.startswith(f"{doc_id}_chunks.") or fname.startswith(f"{doc_id}_embeddings."):
                    self._safe_remove(os.path.join(self.processed_dir, fname))

        # Delete from SQLite (cascades to chunks table via FOREIGN KEY ON DELETE CASCADE)
        with self._get_connection() as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE;")
            try:
                conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise

        return True


embedding_service = EmbeddingService()
