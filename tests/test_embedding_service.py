"""Tests for EmbeddingService: Concurrency control, transactional manifest protocol,
all 8 crash recovery scenarios, and recoverable document deletion.
"""

import os
import json
import shutil
import sqlite3
import hashlib
import tempfile
import unittest
import threading
import numpy as np

from backend.app.rag.chunker import DocumentChunker, SimpleWhitespaceTokenizer
from backend.app.rag.embedder import DenseEmbedder
from backend.app.services.document_service import DocumentService
from backend.app.services.embedding_service import (
    EmbeddingService,
    ConcurrencyConflictError,
    DocumentNotFoundError,
    InvalidDocumentStateError,
    compute_file_sha256,
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'PROCESSING_EMBEDDINGS', staged_tx_id = 'tx_concurrent_lock' WHERE doc_id = ?",
                (self.doc_id,),
            )
            conn.commit()

        with self.assertRaises(ConcurrencyConflictError) as ctx:
            self.service.process_document(self.doc_id)
        self.assertIn("currently being processed", str(ctx.exception))

    def test_concurrent_processing_separate_sqlite_connections(self):
        """Test multi-threaded concurrent lock acquisition across separate SQLite connections."""
        results = []
        errors = []

        def worker(worker_id: int):
            tx = f"tx_thread_{worker_id}"
            try:
                # Each thread uses separate SQLite connection via service
                rec = self.service.acquire_processing_lock(self.doc_id, tx)
                results.append((worker_id, tx))
            except ConcurrencyConflictError as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly 1 thread must acquire lock; other 4 must receive ConcurrencyConflictError
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 4)

    def test_reprocessing_without_force_rejected_with_force_succeeds(self):
        """Test that an already INDEXED document requires force=True to reprocess."""
        self.service.process_document(self.doc_id)

        with self.assertRaises(ConcurrencyConflictError) as ctx:
            self.service.process_document(self.doc_id, force=False)
        self.assertIn("Allowed statuses for processing", str(ctx.exception))

        re_res = self.service.process_document(self.doc_id, force=True)
        self.assertEqual(re_res.status, "INDEXED")

    def test_failed_reindex_preserves_previous_valid_indexed_version(self):
        """Verify that a failed re-indexing run preserves the pre-existing valid indexed artifacts."""
        # 1. Establish valid indexed state
        init_res = self.service.process_document(self.doc_id)
        self.assertEqual(init_res.status, "INDEXED")

        active_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        active_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy")
        initial_chunks_sha = compute_file_sha256(active_chunks)
        initial_emb_sha = compute_file_sha256(active_emb)

        # 2. Simulate re-indexing crash during rotation
        tx_id = "tx_failed_reindex"
        staged_chunks = f"{active_chunks}.staged_{tx_id}"
        staged_emb = f"{active_emb}.staged_{tx_id}"
        backup_chunks = f"{active_chunks}.backup_{tx_id}"
        backup_emb = f"{active_emb}.backup_{tx_id}"

        with open(staged_chunks, "w") as f:
            f.write('[{"chunk_id": "new"}]')
        with open(staged_emb, "wb") as f:
            np.save(f, np.ones((1, 384), dtype=np.float32))

        # Rotate only chunks to simulate crash mid-rotation
        os.replace(active_chunks, backup_chunks)
        os.replace(staged_chunks, active_chunks)

        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "ROTATING",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": True, "embeddings_file": True},
            "files": {
                "chunks": {
                    "active_path": active_chunks,
                    "staged_path": staged_chunks,
                    "backup_path": backup_chunks,
                    "expected_sha256": compute_file_sha256(active_chunks),
                    "rotated": True,
                },
                "embeddings": {
                    "active_path": active_emb,
                    "staged_path": staged_emb,
                    "backup_path": backup_emb,
                    "expected_sha256": compute_file_sha256(staged_emb),
                    "rotated": False,
                },
            },
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # 3. Startup recovery executes rollback
        res = self.service.startup_recovery_scan()
        self.assertEqual(res["rolled_back"], 1)

        # 4. Verify previous artifacts restored completely
        self.assertTrue(os.path.exists(active_chunks))
        self.assertTrue(os.path.exists(active_emb))
        self.assertEqual(compute_file_sha256(active_chunks), initial_chunks_sha)
        self.assertEqual(compute_file_sha256(active_emb), initial_emb_sha)

    # -------------------------------------------------------------------------
    # Individual Tests for All Eight Crash Points (Plan v3.2)
    # -------------------------------------------------------------------------

    def test_crash_point_1_in_memory_chunking_inference(self):
        """Crash Point 1: Crash during in-memory chunking or embedding inference before staging files."""
        tx_id = "tx_cp1"
        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "STAGING",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": False, "embeddings_file": False},
            "files": {
                "chunks": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json"),
                    "staged_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.staged_{tx_id}"),
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.backup_{tx_id}"),
                },
                "embeddings": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy"),
                    "staged_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.staged_{tx_id}"),
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.backup_{tx_id}"),
                },
            },
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'PROCESSING_EMBEDDINGS', staged_tx_id = ? WHERE doc_id = ?",
                (tx_id, self.doc_id),
            )
            conn.commit()

        res = self.service.startup_recovery_scan()
        self.assertEqual(res["rolled_back"], 1)
        self.assertFalse(os.path.exists(manifest_path))

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (self.doc_id,)).fetchone()
            self.assertEqual(doc["status"], "FAILED")
            self.assertIsNone(doc["staged_tx_id"])

    def test_crash_point_2_during_staging_files_exist(self):
        """Crash Point 2: Crash after writing .staged_{tx_id} files, manifest in STAGED."""
        tx_id = "tx_cp2"
        staged_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.staged_{tx_id}")
        staged_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.staged_{tx_id}")
        with open(staged_chunks, "w") as f:
            f.write("[]")
        with open(staged_emb, "wb") as f:
            np.save(f, np.zeros((1, 384), dtype=np.float32))

        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "STAGED",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": False, "embeddings_file": False},
            "files": {
                "chunks": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json"),
                    "staged_path": staged_chunks,
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.backup_{tx_id}"),
                    "expected_sha256": compute_file_sha256(staged_chunks),
                },
                "embeddings": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy"),
                    "staged_path": staged_emb,
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.backup_{tx_id}"),
                    "expected_sha256": compute_file_sha256(staged_emb),
                },
            },
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        res = self.service.startup_recovery_scan()
        self.assertEqual(res["rolled_back"], 1)
        self.assertFalse(os.path.exists(staged_chunks))
        self.assertFalse(os.path.exists(staged_emb))
        self.assertFalse(os.path.exists(manifest_path))

    def test_crash_point_3_asymmetric_file_rotation(self):
        """Crash Point 3: Crash between the two file replacements during rotation."""
        tx_id = "tx_cp3"
        active_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        backup_chunks = f"{active_chunks}.backup_{tx_id}"
        active_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy")
        staged_emb = f"{active_emb}.staged_{tx_id}"

        # Prior active state
        with open(backup_chunks, "w") as f:
            f.write('[{"chunk_id": "old_backup"}]')
        with open(active_chunks, "w") as f:
            f.write('[{"chunk_id": "new_rotated"}]')
        with open(active_emb, "wb") as f:
            np.save(f, np.zeros((1, 384), dtype=np.float32))  # Old unrotated active
        with open(staged_emb, "wb") as f:
            np.save(f, np.ones((1, 384), dtype=np.float32))  # New staged

        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "ROTATING",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": True, "embeddings_file": True},
            "files": {
                "chunks": {
                    "active_path": active_chunks,
                    "staged_path": f"{active_chunks}.staged_{tx_id}",
                    "backup_path": backup_chunks,
                    "expected_sha256": compute_file_sha256(active_chunks),
                    "rotated": True,
                },
                "embeddings": {
                    "active_path": active_emb,
                    "staged_path": staged_emb,
                    "backup_path": f"{active_emb}.backup_{tx_id}",
                    "expected_sha256": compute_file_sha256(staged_emb),
                    "rotated": False,
                },
            },
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        res = self.service.startup_recovery_scan()
        self.assertEqual(res["rolled_back"], 1)

        # Chunks restored from backup; embeddings left intact; staged unlinked
        with open(active_chunks, "r") as f:
            data = json.load(f)
        self.assertEqual(data[0]["chunk_id"], "old_backup")
        self.assertFalse(os.path.exists(backup_chunks))
        self.assertFalse(os.path.exists(staged_emb))

    def test_crash_point_4_full_rollback_before_db_commit(self):
        """Crash Point 4: Both files rotated, both backups exist, crash before SQLite commit."""
        tx_id = "tx_cp4"
        active_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        backup_chunks = f"{active_chunks}.backup_{tx_id}"
        active_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy")
        backup_emb = f"{active_emb}.backup_{tx_id}"

        with open(backup_chunks, "w") as f:
            f.write('[{"chunk_id": "original_chunks"}]')
        with open(active_chunks, "w") as f:
            f.write('[{"chunk_id": "new_uncommitted"}]')

        with open(backup_emb, "wb") as f:
            np.save(f, np.zeros((1, 384), dtype=np.float32))
        with open(active_emb, "wb") as f:
            np.save(f, np.ones((1, 384), dtype=np.float32))

        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "ROTATED",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": True, "embeddings_file": True},
            "files": {
                "chunks": {
                    "active_path": active_chunks,
                    "staged_path": f"{active_chunks}.staged_{tx_id}",
                    "backup_path": backup_chunks,
                    "expected_sha256": compute_file_sha256(active_chunks),
                    "rotated": True,
                },
                "embeddings": {
                    "active_path": active_emb,
                    "staged_path": f"{active_emb}.staged_{tx_id}",
                    "backup_path": backup_emb,
                    "expected_sha256": compute_file_sha256(active_emb),
                    "rotated": True,
                },
            },
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        res = self.service.startup_recovery_scan()
        self.assertEqual(res["rolled_back"], 1)

        with open(active_chunks, "r") as f:
            data = json.load(f)
        self.assertEqual(data[0]["chunk_id"], "original_chunks")
        vec = np.load(active_emb)
        self.assertEqual(vec[0][0], 0.0)

    def test_crash_point_5_db_commit_failure_rollback(self):
        """Crash Point 5: SQLite commit aborted / rolled back."""
        tx_id = "tx_cp5"
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "DB_COMMITTING",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": False, "embeddings_file": False},
            "files": {
                "chunks": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json"),
                    "staged_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.staged_{tx_id}"),
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json.backup_{tx_id}"),
                },
                "embeddings": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy"),
                    "staged_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.staged_{tx_id}"),
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.backup_{tx_id}"),
                },
            },
        }
        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'PROCESSING_EMBEDDINGS', staged_tx_id = ? WHERE doc_id = ?",
                (tx_id, self.doc_id),
            )
            conn.commit()

        res = self.service.startup_recovery_scan()
        self.assertEqual(res["rolled_back"], 1)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (self.doc_id,)).fetchone()
            self.assertEqual(doc["status"], "FAILED")

    def test_crash_point_6_post_commit_crash_before_manifest_db_committed(self):
        """Crash Point 6: SQLite committed, but crash occurred before manifest db_committed was written."""
        tx_id = "tx_cp6"
        active_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        active_emb = os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy")
        backup_chunks = f"{active_chunks}.backup_{tx_id}"

        with open(active_chunks, "w") as f:
            f.write('[{"chunk_id": "committed_chunk"}]')
        np.save(active_emb, np.zeros((1, 384), dtype=np.float32))
        with open(backup_chunks, "w") as f:
            f.write("[]")

        # Manifest has db_committed = False, simulating crash immediately prior to manifest write!
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "ROTATED",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": True, "embeddings_file": True},
            "files": {
                "chunks": {
                    "active_path": active_chunks,
                    "staged_path": f"{active_chunks}.staged_{tx_id}",
                    "backup_path": backup_chunks,
                    "expected_sha256": compute_file_sha256(active_chunks),
                },
                "embeddings": {
                    "active_path": active_emb,
                    "staged_path": f"{active_emb}.staged_{tx_id}",
                    "backup_path": f"{active_emb}.backup_{tx_id}",
                    "expected_sha256": compute_file_sha256(active_emb),
                },
            },
        }
        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # But SQLite committed successfully!
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'INDEXED', active_tx_id = ?, staged_tx_id = NULL WHERE doc_id = ?",
                (tx_id, self.doc_id),
            )
            conn.commit()

        res = self.service.startup_recovery_scan()
        # Recovery inspects DB active_tx_id == tx_id and validates checksums -> resolves and finalizes!
        self.assertEqual(res["resolved"], 1)
        self.assertTrue(os.path.exists(active_chunks))
        self.assertTrue(os.path.exists(active_emb))
        self.assertFalse(os.path.exists(backup_chunks))
        self.assertFalse(os.path.exists(manifest_path))

    def test_crash_point_7_corrupted_backup_triggers_quarantine(self):
        """Crash Point 7: Pre-existing active was rotated, but backup is missing -> Non-destructive quarantine."""
        tx_id = "tx_cp7"
        active_chunks = os.path.join(self.processed_dir, f"{self.doc_id}_chunks.json")
        with open(active_chunks, "w") as f:
            f.write('[{"chunk_id": "new_rotated_chunks"}]')

        # active_files_pre_existing = True, rotated = True, but backup_path DOES NOT EXIST!
        manifest = {
            "tx_id": tx_id,
            "doc_id": self.doc_id,
            "stage": "ROTATING",
            "db_committed": False,
            "active_files_pre_existing": {"chunks_file": True, "embeddings_file": False},
            "files": {
                "chunks": {
                    "active_path": active_chunks,
                    "staged_path": f"{active_chunks}.staged_{tx_id}",
                    "backup_path": f"{active_chunks}.backup_{tx_id}",
                    "expected_sha256": compute_file_sha256(active_chunks),
                    "rotated": True,
                },
                "embeddings": {
                    "active_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy"),
                    "staged_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.staged_{tx_id}"),
                    "backup_path": os.path.join(self.processed_dir, f"{self.doc_id}_embeddings.npy.backup_{tx_id}"),
                    "expected_sha256": None,
                    "rotated": False,
                },
            },
        }
        manifest_path = os.path.join(self.processed_dir, f"{self.doc_id}_{tx_id}.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        res = self.service.startup_recovery_scan()
        self.assertEqual(res["quarantined"], 1)

        # Check that quarantine directory was created and status updated to MANUAL_RECOVERY_REQUIRED
        quarantine_dirs = [d for d in os.listdir(self.processed_dir) if "quarantine" in d]
        self.assertEqual(len(quarantine_dirs), 1)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (self.doc_id,)).fetchone()
            self.assertEqual(doc["status"], "MANUAL_RECOVERY_REQUIRED")

    def test_crash_point_8_interrupted_deletion_recovery(self):
        """Crash Point 8: Process crashed during document deletion with status = 'DELETING'."""
        # Create residual files
        residual_raw = os.path.join(self.raw_dir, f"{self.doc_id}.pdf")
        residual_proc = os.path.join(self.processed_dir, f"{self.doc_id}.json")
        with open(residual_raw, "wb") as f:
            f.write(b"%PDF-1.4...")
        with open(residual_proc, "w") as f:
            f.write("{}")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'DELETING' WHERE doc_id = ?",
                (self.doc_id,),
            )
            conn.commit()

        # Startup recovery scans and completes interrupted deletion
        self.service.startup_recovery_scan()

        self.assertFalse(os.path.exists(residual_raw))
        self.assertFalse(os.path.exists(residual_proc))

        with sqlite3.connect(self.db_path) as conn:
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (self.doc_id,)).fetchone()
            self.assertIsNone(doc)


if __name__ == "__main__":
    unittest.main()
