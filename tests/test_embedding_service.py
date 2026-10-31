"""Tests for EmbeddingService: Concurrency control, transactional manifest protocol,
crash recovery (points 1-8), and recoverable document deletion.
"""

import os
import json
import shutil
import sqlite3
import hashlib
import tempfile
import unittest
import numpy as np

from backend.app.rag.chunker import DocumentChunker, SimpleWhitespaceTokenizer
from backend.app.rag.embedder import DenseEmbedder
from backend.app.services.document_service import DocumentService
from backend.app.services.embedding_service import (
    EmbeddingService,
    ConcurrencyConflictError,
    DocumentNotFoundError,
    InvalidDocumentStateError,
)
from tests.synthetic_pdf_generator import create_valid_multipage_pdf, create_empty_pdf


class TestEmbeddingService(unittest.TestCase):
    """Test suite for transactional document chunking, embedding generation, CAS locking, and recovery."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="unimind_test_emb_")
        self.raw_dir = os.path.join(self.test_dir, "raw")
        self.processed_dir = os.path.join(self.test_dir, "processed")
        self.db_path = os.path.join(self.test_dir, "test_unimind.db")

        # Initialize mock embedder and fast whitespace tokenizer for sub-second isolated tests
        self.mock_embedder = DenseEmbedder(use_mock=True)
        self.chunker = DocumentChunker(tokenizer=SimpleWhitespaceTokenizer(), target_chunk_size=100, chunk_overlap=20)

        self.doc_service = DocumentService(db_path=self.db_path)
        self.doc_service.raw_dir = self.raw_dir
        self.doc_service.processed_dir = self.processed_dir
        self.doc_service._init_storage()

        self.service = EmbeddingService(
            db_path=self.db_path,
            chunker=self.chunker,
            embedder=self.mock_embedder,
        )
        self.service.raw_dir = self.raw_dir
        self.service.processed_dir = self.processed_dir

        # Ingest a standard synthetic document
        pdf_bytes = create_valid_multipage_pdf()
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        upload_res = self.doc_service.ingest_document(
            file_bytes=pdf_bytes,
            filename="synthetic_policy.pdf",
            file_hash=pdf_hash,
            department="Academic Affairs",
            category="Policy",
        )
        self.doc_id = upload_res["doc_id"]

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_successful_document_processing_lifecycle(self):
        """Test full processing pipeline: STAGING -> ROTATING -> DB_COMMITTING -> COMMITTED -> finalized."""
        res = self.service.process_document(self.doc_id)

        self.assertEqual(res.status, "INDEXED")
        self.assertGreater(res.total_chunks, 0)
        self.assertEqual(res.vector_dimension, 384)

        # Check active files exist on disk
        active_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        active_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy")
        self.assertTrue(os.path.exists(active_chunks))
        self.assertTrue(os.path.exists(active_emb))

        # Check vector format and shape
        vectors = np.load(active_emb)
        self.assertEqual(vectors.shape, (res.total_chunks, 384))
        self.assertEqual(vectors.dtype, np.float32)

        # Check database records
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (self.doc_id,)).fetchone()
            self.assertEqual(doc["status"], "INDEXED")
            self.assertEqual(doc["total_chunks"], res.total_chunks)
            self.assertIsNotNone(doc["active_tx_id"])
            self.assertIsNone(doc["staged_tx_id"])

            chunks_in_db = conn.execute("SELECT * FROM chunks WHERE doc_id = ?", (self.doc_id,)).fetchall()
            self.assertEqual(len(chunks_in_db), res.total_chunks)

        # Check that no manifest or temporary staged/backup files linger
        lingering = [f for f in os.listdir(self.processed_dir) if "manifest" in f or "staged" in f or "backup" in f]
        self.assertEqual(len(lingering), 0)

    def test_concurrency_lock_prevents_duplicate_processing(self):
        """Test that CAS lock raises ConcurrencyConflictError when document is already being processed."""
        # Simulate an ongoing transaction holding the CAS lock
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'PROCESSING_EMBEDDINGS', staged_tx_id = 'tx_concurrent_lock' WHERE doc_id = ?",
                (self.doc_id,),
            )
            conn.commit()

        with self.assertRaises(ConcurrencyConflictError) as ctx:
            self.service.process_document(self.doc_id)
        self.assertIn("currently being processed", str(ctx.exception))

    def test_reprocessing_without_force_rejected_with_force_succeeds(self):
        """Test that an already INDEXED document requires force=True to reprocess."""
        # First processing run
        self.service.process_document(self.doc_id)

        # Second processing without force -> Conflict
        with self.assertRaises(ConcurrencyConflictError) as ctx:
            self.service.process_document(self.doc_id, force=False)
        self.assertIn("Allowed statuses for processing", str(ctx.exception))

        # Reprocessing with force=True -> Success
        re_res = self.service.process_document(self.doc_id, force=True)
        self.assertEqual(re_res.status, "INDEXED")

    def test_crash_recovery_uncommitted_with_staged_files(self):
        """Test Crash Point 3: Crash occurred while staging files before DB commit."""
        tx_id = "tx_crash_stage_test"
        # Manually create staged files and an uncommitted manifest
        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        staged_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.staged_{tx_id}")
        staged_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.staged_{tx_id}")

        with open(staged_chunks, "w") as f:
            f.write("[]")
        np.save(staged_emb, np.zeros((1, 384), dtype=np.float32))

        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "STAGING",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": False, "embeddings_file": False},
            "files": {
                "chunks": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json"),
                    "staged_path": staged_chunks,
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.backup_{tx_id}"),
                },
                "embeddings": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy"),
                    "staged_path": staged_emb,
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.backup_{tx_id}"),
                },
            },
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Set document status to PROCESSING_EMBEDDINGS with staged_tx_id
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'PROCESSING_EMBEDDINGS', staged_tx_id = ? WHERE doc_id = ?",
                (tx_id, self.doc_id),
            )
            conn.commit()

        # Run startup recovery scan
        results = self.service.startup_recovery_scan()
        self.assertEqual(results["rolled_back"], 1)

        # Staged files and manifest must be cleanly deleted
        self.assertFalse(os.path.exists(staged_chunks))
        self.assertFalse(os.path.exists(staged_emb))
        self.assertFalse(os.path.exists(manifest_path))

        # Document status should be reverted
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (self.doc_id,)).fetchone()
            self.assertEqual(doc["status"], "FAILED")

    def test_crash_recovery_committed_finalizes_artifacts(self):
        """Test Crash Point 7: DB committed but crash occurred before deleting backups and manifest."""
        tx_id = "tx_crash_commit_test"
        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        active_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        active_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy")
        backup_chunks = f"{active_chunks}.backup_{tx_id}"

        # Create active files and dummy backup
        with open(active_chunks, "w") as f:
            f.write("[]")
        np.save(active_emb, np.zeros((1, 384), dtype=np.float32))
        with open(backup_chunks, "w") as f:
            f.write("[]")

        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "COMMITTED",
            "db_committed": True,
            "active_files_pre_existing": {"chunks_file": True, "embeddings_file": True},
            "files": {
                "chunks": {
                    "active_path": active_chunks,
                    "staged_path": f"{active_chunks}.staged_{tx_id}",
                    "backup_path": backup_chunks,
                },
                "embeddings": {
                    "active_path": active_emb,
                    "staged_path": f"{active_emb}.staged_{tx_id}",
                    "backup_path": f"{active_emb}.backup_{tx_id}",
                },
            },
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Set DB to INDEXED with this tx_id
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'INDEXED', active_tx_id = ? WHERE doc_id = ?",
                (tx_id, self.doc_id),
            )
            conn.commit()

        # Execute recovery scan
        results = self.service.startup_recovery_scan()
        self.assertEqual(results["resolved"], 1)

        # Backup and manifest should be cleaned; active files preserved
        self.assertTrue(os.path.exists(active_chunks))
        self.assertTrue(os.path.exists(active_emb))
        self.assertFalse(os.path.exists(backup_chunks))
        self.assertFalse(os.path.exists(manifest_path))

    def test_recoverable_deletion_workflow(self):
        """Test recoverable document deletion cleans raw, processed, chunk, and embedding artifacts."""
        # First process the document
        self.service.process_document(self.doc_id)

        # Ensure artifacts exist
        raw_pdf = os.path.join(self.raw_dir, f"{self.doc_id}.pdf")
        proc_json = os.path.join(self.processed_dir, f"{self.doc_id}.json")
        proc_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        proc_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy")
        self.assertTrue(os.path.exists(raw_pdf))
        self.assertTrue(os.path.exists(proc_json))
        self.assertTrue(os.path.exists(proc_chunks))
        self.assertTrue(os.path.exists(proc_emb))

        # Execute recoverable deletion
        success = self.service.delete_document_recoverable(self.doc_id)
        self.assertTrue(success)

        # Verify all files are deleted
        self.assertFalse(os.path.exists(raw_pdf))
        self.assertFalse(os.path.exists(proc_json))
        self.assertFalse(os.path.exists(proc_chunks))
        self.assertFalse(os.path.exists(proc_emb))

        # Verify DB records deleted (including foreign key cascade on chunks)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (self.doc_id,)).fetchone()
            chunks = conn.execute("SELECT * FROM chunks WHERE doc_id = ?", (self.doc_id,)).fetchall()
            self.assertIsNone(doc)
            self.assertEqual(len(chunks), 0)


if __name__ == "__main__":
    unittest.main()
