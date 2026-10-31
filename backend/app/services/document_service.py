"""Document Ingestion Service: Storage, SQLite Registry, and Lifecycle Management."""

import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.app.core.config import settings
from backend.app.rag.parser import parse_pdf_document


def atomic_write(filepath: str, data: Any) -> None:
    """Perform an atomic write by writing to a temporary file and atomically replacing the target.

    Args:
        filepath: Final destination path.
        data: String, bytes, or JSON-serializable dictionary.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    temp_path = f"{filepath}.tmp_{uuid.uuid4().hex}"

    if isinstance(data, bytes):
        with open(temp_path, "wb") as f:
            f.write(data)
    elif isinstance(data, str):
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(data)
    else:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(temp_path, filepath)


class DocumentService:
    """Manages document validation, parsing, SQLite registry tracking, and persistence."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self.raw_dir = settings.DATA_RAW_DIR
        self.processed_dir = settings.DATA_PROCESSED_DIR
        self._init_storage()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a SQLite connection with row dictionary access and busy timeout."""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_storage(self) -> None:
        """Ensure storage directories and SQLite registry schema are initialized."""
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL UNIQUE,
                    file_size_bytes INTEGER NOT NULL,
                    total_pages INTEGER NOT NULL,
                    department TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    has_scanned_pages INTEGER NOT NULL DEFAULT 0,
                    needs_ocr_review INTEGER NOT NULL DEFAULT 0,
                    is_empty INTEGER NOT NULL DEFAULT 0,
                    total_words INTEGER NOT NULL DEFAULT 0,
                    total_characters INTEGER NOT NULL DEFAULT 0,
                    raw_file_path TEXT NOT NULL,
                    processed_file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);")
            conn.commit()

    def get_document_by_hash(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve an existing document record by its SHA-256 checksum."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document record by UUID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def list_documents(self, department: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List ingested documents, optionally filtered by department, without exposing filesystem paths."""
        query = "SELECT * FROM documents"
        params: List[Any] = []

        if department:
            query += " WHERE department = ?"
            params.append(department)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                doc_dict = self._sanitize_record_for_api(dict(r))
                results.append(doc_dict)
            return results

    def ingest_document(
        self,
        file_bytes: bytes,
        filename: str,
        file_hash: str,
        department: str = "General",
        category: str = "Policy",
    ) -> Dict[str, Any]:
        """Ingest, parse, and persist a validated PDF document.

        Handles duplicate detection, status transitions (PROCESSING -> PROCESSED/FAILED),
        atomic raw/processed disk writes, and registry updates.

        Args:
            file_bytes: Binary bytes of the PDF.
            filename: Sanitized original filename.
            file_hash: SHA-256 checksum.
            department: University department.
            category: Document category.

        Returns:
            Dictionary matching DocumentUploadResponse schema without local filesystem paths.
        """
        # 1. Duplicate upload handling
        existing = self.get_document_by_hash(file_hash)
        if existing and existing["status"] == "PROCESSED":
            # Retrieve processed JSON content for page snippets
            pages = self._load_processed_pages(existing["processed_file_path"])
            sanitized = self._sanitize_record_for_api(existing)
            sanitized["is_duplicate"] = True
            sanitized["pages"] = pages
            return sanitized

        now_iso = datetime.now(timezone.utc).isoformat()
        doc_id = str(uuid.uuid4())
        raw_path = os.path.join(self.raw_dir, f"{doc_id}.pdf")
        processed_path = os.path.join(self.processed_dir, f"{doc_id}.json")
        file_size = len(file_bytes)

        # 2. PyMuPDF parsing & layout extraction (validates in memory before writing to disk)
        parse_result = parse_pdf_document(file_bytes=file_bytes, filename=filename)

        # 3. Register with PROCESSING status
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    doc_id, filename, file_hash, file_size_bytes, total_pages,
                    department, category, status, has_scanned_pages, needs_ocr_review,
                    is_empty, total_words, total_characters, raw_file_path,
                    processed_file_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id, filename, file_hash, file_size, parse_result["total_pages"],
                    department, category, "PROCESSING", int(parse_result["has_scanned_pages"]),
                    int(parse_result["needs_ocr_review"]), int(parse_result["is_empty"]),
                    parse_result["total_words"], parse_result["total_characters"],
                    raw_path, processed_path, now_iso, now_iso,
                ),
            )
            conn.commit()

        try:
            # 4. Atomic write of original raw PDF
            atomic_write(raw_path, file_bytes)

            # 5. Atomic write of processed structured JSON
            processed_data = {
                "doc_id": doc_id,
                "filename": filename,
                "file_hash": file_hash,
                "department": department,
                "category": category,
                "extracted_at": now_iso,
                "doc_metadata": parse_result["doc_metadata"],
                "total_pages": parse_result["total_pages"],
                "total_words": parse_result["total_words"],
                "total_characters": parse_result["total_characters"],
                "is_empty": parse_result["is_empty"],
                "has_scanned_pages": parse_result["has_scanned_pages"],
                "needs_ocr_review": parse_result["needs_ocr_review"],
                "pages": parse_result["pages"],
            }
            atomic_write(processed_path, processed_data)

            # 6. Update status to PROCESSED
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE documents SET
                        status = 'PROCESSED',
                        updated_at = ?
                    WHERE doc_id = ?
                    """,
                    (
                        datetime.now(timezone.utc).isoformat(),
                        doc_id,
                    ),
                )
                conn.commit()

            # Retrieve clean record for API response
            updated = self.get_document_by_id(doc_id)
            sanitized = self._sanitize_record_for_api(updated or {})
            sanitized["is_duplicate"] = False
            sanitized["pages"] = parse_result["pages"]
            return sanitized

        except Exception as e:
            # Transition status to FAILED and record error message
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE documents SET
                        status = 'FAILED',
                        error_message = ?,
                        updated_at = ?
                    WHERE doc_id = ?
                    """,
                    (str(e), datetime.now(timezone.utc).isoformat(), doc_id),
                )
                conn.commit()
            raise e

    def get_document_details(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full document details, metadata, and extracted pages by doc_id."""
        record = self.get_document_by_id(doc_id)
        if not record:
            return None

        sanitized = self._sanitize_record_for_api(record)
        pages = self._load_processed_pages(record["processed_file_path"])
        sanitized["pages"] = pages
        return sanitized

    def delete_document(self, doc_id: str) -> bool:
        """Safely delete a document, its raw file, processed JSON, and registry entry.

        Args:
            doc_id: UUID of the document to delete.

        Returns:
            True if deleted, False if document did not exist.
        """
        record = self.get_document_by_id(doc_id)
        if not record:
            return False

        # 1. Delete raw PDF file if exists
        raw_path = record.get("raw_file_path")
        if raw_path and os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except OSError:
                pass

        # 2. Delete processed JSON file if exists
        processed_path = record.get("processed_file_path")
        if processed_path and os.path.exists(processed_path):
            try:
                os.remove(processed_path)
            except OSError:
                pass

        # 3. Delete SQLite registry record
        with self._get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.commit()

        return True

    def _load_processed_pages(self, processed_file_path: str) -> List[Dict[str, Any]]:
        """Load page objects from processed JSON storage."""
        if processed_file_path and os.path.exists(processed_file_path):
            try:
                with open(processed_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("pages", [])
            except Exception:
                pass
        return []

    def _sanitize_record_for_api(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Strip internal filesystem paths and return clean public API dictionary."""
        return {
            "doc_id": record.get("doc_id"),
            "filename": record.get("filename"),
            "file_hash_sha256": record.get("file_hash"),
            "file_size_bytes": record.get("file_size_bytes", 0),
            "total_pages": record.get("total_pages", 0),
            "department": record.get("department", "General"),
            "category": record.get("category", "Policy"),
            "status": record.get("status", "UNKNOWN"),
            "has_scanned_pages": bool(record.get("has_scanned_pages", 0)),
            "needs_ocr_review": bool(record.get("needs_ocr_review", 0)),
            "is_empty": bool(record.get("is_empty", 0)),
            "total_words": record.get("total_words", 0),
            "total_characters": record.get("total_characters", 0),
            "uploaded_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "error_message": record.get("error_message"),
        }


document_service = DocumentService()

