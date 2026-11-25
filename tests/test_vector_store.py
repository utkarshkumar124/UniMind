"""Unit tests for FAISS vector store, generation bundles, persistence, and recovery."""

import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import faiss
import numpy as np

from backend.app.rag.vector_store import (
    VectorStoreService,
    VectorStoreLock,
    VectorStoreError,
    VectorStoreMutationError,
    VectorStoreLockConflictError,
    VectorStoreCorruptionError,
    VectorStoreNotReadyError,
    GenerationSnapshot,
    ReadOnlyFAISSIndex,
    compute_file_sha256,
    fsync_dir,
)


def _lock_worker_process(lock_path_str: str, command_queue, response_queue):
    """Child worker process to test genuine cross-process lock contention."""
    from pathlib import Path
    from backend.app.rag.vector_store import VectorStoreLock, VectorStoreLockConflictError

    lock = VectorStoreLock(Path(lock_path_str), timeout_seconds=0.0)
    while True:
        try:
            cmd = command_queue.get(timeout=10.0)
        except Exception:
            break
        if cmd == "ACQUIRE":
            try:
                lock.acquire()
                response_queue.put(("ACQUIRED", None))
            except VectorStoreLockConflictError as e:
                response_queue.put(("CONFLICT", str(e)))
            except Exception as e:
                response_queue.put(("ERROR", str(e)))
        elif cmd == "RELEASE":
            try:
                lock.release()
                response_queue.put(("RELEASED", None))
            except Exception as e:
                response_queue.put(("ERROR", str(e)))
        elif cmd == "STOP":
            break


class TestVectorStoreFoundation(unittest.TestCase):
    """Test suite for FAISS generation bundle foundation (Milestone 1)."""

    def setUp(self):
        """Set up an isolated temporary directory for vector store tests."""
        self.test_dir = tempfile.mkdtemp(prefix="unimind_vstore_test_")
        self.service = VectorStoreService(index_dir=self.test_dir)

    def tearDown(self):
        """Clean up the temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_sample_vectors_and_metadata(self, count: int = 5, dim: int = 384):
        """Helper to create normalized float32 vectors, FAISS index, and mock metadata."""
        flat_index = faiss.IndexFlatIP(dim)
        index = faiss.IndexIDMap2(flat_index)

        rng = np.random.RandomState(42)
        raw_vecs = rng.randn(count, dim).astype(np.float32)
        faiss.normalize_L2(raw_vecs)
        ids = np.arange(1, count + 1, dtype=np.int64)
        index.add_with_ids(raw_vecs, ids)

        int_to_chunk_id = {}
        chunk_id_to_int = {}
        chunk_metadata = {}
        doc_id = "doc_test_uuid_001"
        doc_chunk_ids = []

        for idx, i_id in enumerate(ids):
            cid = f"{doc_id}#p1#c{idx}"
            int_to_chunk_id[int(i_id)] = cid
            chunk_id_to_int[cid] = int(i_id)
            doc_chunk_ids.append(cid)
            chunk_metadata[cid] = {
                "text": f"Sample academic passage chunk {idx}",
                "doc_id": doc_id,
                "page_start": 1,
                "page_end": 1,
                "chunk_index": idx,
                "department": "Academic Affairs",
                "category": "Regulations",
                "file_hash": "sha256_mock_hash",
            }

        metadata = {
            "int_to_chunk_id": int_to_chunk_id,
            "chunk_id_to_int": chunk_id_to_int,
            "doc_id_to_chunk_ids": {doc_id: doc_chunk_ids},
            "chunk_metadata": chunk_metadata,
            "next_id": count + 1,
        }
        return index, metadata

    def test_successful_generation_bundle_creation_and_loading(self):
        """Verify immutable generation bundle creation, SHA-256 computation, and loading."""
        index, metadata = self._create_sample_vectors_and_metadata(count=5)
        snapshot = self.service.commit_generation_bundle(index, metadata)

        # 1. Verify bundle files on disk
        gen_dir = snapshot.directory
        self.assertTrue(gen_dir.is_dir())
        self.assertTrue((gen_dir / "index.faiss").exists())
        self.assertTrue((gen_dir / "metadata.json").exists())
        self.assertTrue((gen_dir / "manifest.json").exists())

        # 2. Verify manifest integrity
        with open(gen_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["generation_id"], snapshot.generation_id)
        self.assertEqual(manifest["total_vectors"], 5)
        self.assertEqual(manifest["total_chunks"], 5)
        self.assertEqual(manifest["total_documents"], 1)
        self.assertEqual(manifest["state"], "COMMITTED")
        self.assertEqual(manifest["dimension"], 384)
        self.assertEqual(manifest["metric"], "INNER_PRODUCT")

        # 3. Verify SHA-256 hashes
        actual_index_hash = compute_file_sha256(gen_dir / "index.faiss")
        actual_meta_hash = compute_file_sha256(gen_dir / "metadata.json")
        self.assertEqual(manifest["index_sha256"], actual_index_hash)
        self.assertEqual(manifest["metadata_sha256"], actual_meta_hash)

        # 4. Verify authoritative pointer file
        pointer_file = self.service.pointer_file
        self.assertTrue(pointer_file.exists())
        with open(pointer_file, "r", encoding="utf-8") as f:
            pointer_data = json.load(f)
        self.assertEqual(pointer_data["active_generation_id"], snapshot.generation_id)

        # 5. Load active generation into a new service instance
        service2 = VectorStoreService(index_dir=self.test_dir)
        loaded = service2.load_active_generation()
        self.assertEqual(loaded.generation_id, snapshot.generation_id)
        self.assertEqual(loaded.total_vectors, 5)
        self.assertEqual(loaded.total_chunks, 5)
        self.assertEqual(loaded.total_documents, 1)
        self.assertEqual(len(loaded.int_to_chunk_id), 5)
        self.assertEqual(loaded.int_to_chunk_id[1], "doc_test_uuid_001#p1#c0")
        self.assertTrue(service2.is_ready)

    def test_checksum_mismatch_raises_corruption_error(self):
        """Verify that altering index or metadata bytes causes VectorStoreCorruptionError."""
        index, metadata = self._create_sample_vectors_and_metadata(count=3)
        snapshot = self.service.commit_generation_bundle(index, metadata)

        # Tamper with index.faiss by appending a byte
        index_file = snapshot.directory / "index.faiss"
        with open(index_file, "ab") as f:
            f.write(b"\x00")

        # Loading must detect SHA-256 mismatch and fail
        with self.assertRaises(VectorStoreCorruptionError) as ctx:
            self.service.load_generation(snapshot.generation_id)
        self.assertIn("Index checksum mismatch", str(ctx.exception))

        # Tamper with metadata.json
        meta_file = snapshot.directory / "metadata.json"
        with open(meta_file, "a", encoding="utf-8") as f:
            f.write(" ")
        with self.assertRaises(VectorStoreCorruptionError) as ctx:
            self.service.load_generation(snapshot.generation_id)

    def test_atomic_pointer_replacement_and_parent_tracking(self):
        """Verify sequential generations atomically update pointer and link parents."""
        # Generation 1
        index1, meta1 = self._create_sample_vectors_and_metadata(count=3)
        snap1 = self.service.commit_generation_bundle(index1, meta1)

        # Generation 2
        index2, meta2 = self._create_sample_vectors_and_metadata(count=7)
        snap2 = self.service.commit_generation_bundle(
            index2, meta2, parent_generation_id=snap1.generation_id
        )

        self.assertNotEqual(snap1.generation_id, snap2.generation_id)
        self.assertEqual(snap2.manifest["parent_generation_id"], snap1.generation_id)

        # Pointer must reference Generation 2
        with open(self.service.pointer_file, "r", encoding="utf-8") as f:
            pointer_data = json.load(f)
        self.assertEqual(pointer_data["active_generation_id"], snap2.generation_id)

        # Both generation directories exist intact on disk
        self.assertTrue(snap1.directory.exists())
        self.assertTrue(snap2.directory.exists())

    def test_staging_crash_recovery_cleans_orphaned_staged_pointers(self):
        """Verify startup recovery unlinks orphaned staged pointer files without data loss."""
        index, metadata = self._create_sample_vectors_and_metadata(count=4)
        snap = self.service.commit_generation_bundle(index, metadata)

        # Simulate a crash leaving an orphaned staged pointer
        orphaned_staged = self.service.index_dir / "current_generation.json.staged_simulated_crash_uuid"
        with open(orphaned_staged, "w", encoding="utf-8") as f:
            json.dump({"fake": "staged"}, f)
        self.assertTrue(orphaned_staged.exists())

        # Run startup recovery
        service_recovered = VectorStoreService(index_dir=self.test_dir)
        recovered_snap = service_recovered.startup_recovery()

        self.assertEqual(recovered_snap.generation_id, snap.generation_id)
        self.assertFalse(orphaned_staged.exists(), "Orphaned staged pointer should be unlinked")
        self.assertEqual(service_recovered.total_vectors, 4)
        self.assertTrue(service_recovered.is_ready)

    def test_corrupted_active_generation_triggers_rollback_to_parent(self):
        """Verify startup recovery rolls back to valid parent when active generation is corrupted."""
        # Commit Gen 1 (valid parent)
        index1, meta1 = self._create_sample_vectors_and_metadata(count=3)
        snap1 = self.service.commit_generation_bundle(index1, meta1)

        # Commit Gen 2 (child)
        index2, meta2 = self._create_sample_vectors_and_metadata(count=5)
        snap2 = self.service.commit_generation_bundle(
            index2, meta2, parent_generation_id=snap1.generation_id
        )

        # Corrupt Gen 2's index file
        with open(snap2.directory / "index.faiss", "ab") as f:
            f.write(b"\xFF\xFF\xFF")

        # Run startup recovery in a new service instance
        service_recovered = VectorStoreService(index_dir=self.test_dir)
        recovered_snap = service_recovered.startup_recovery()

        # Must have safely rolled back to Gen 1
        self.assertEqual(recovered_snap.generation_id, snap1.generation_id)
        self.assertEqual(service_recovered.total_vectors, 3)
        self.assertTrue(service_recovered.is_ready)

        # Pointer on disk must now point to Gen 1
        with open(service_recovered.pointer_file, "r", encoding="utf-8") as f:
            pointer_data = json.load(f)
        self.assertEqual(pointer_data["active_generation_id"], snap1.generation_id)

    def test_catastrophic_dual_corruption_triggers_quarantine_and_rebuild_required(self):
        """Verify that when both active and parent are corrupted, files are quarantined."""
        index1, meta1 = self._create_sample_vectors_and_metadata(count=2)
        snap1 = self.service.commit_generation_bundle(index1, meta1)

        index2, meta2 = self._create_sample_vectors_and_metadata(count=4)
        snap2 = self.service.commit_generation_bundle(
            index2, meta2, parent_generation_id=snap1.generation_id
        )

        # Corrupt both generations
        with open(snap1.directory / "index.faiss", "ab") as f:
            f.write(b"CORRUPT")
        with open(snap2.directory / "index.faiss", "ab") as f:
            f.write(b"CORRUPT")

        service_recovered = VectorStoreService(index_dir=self.test_dir)
        with self.assertRaises(VectorStoreCorruptionError):
            service_recovered.startup_recovery()

        # State must be REBUILD_REQUIRED
        self.assertEqual(service_recovered.state, "REBUILD_REQUIRED")
        self.assertFalse(service_recovered.is_ready)
        self.assertTrue(service_recovered.quarantine_dir.exists())

    def test_cross_process_file_lock_multiprocessing(self):
        """Verify genuine cross-process mutual exclusion with a separate OS child process."""
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        cmd_q = ctx.Queue()
        resp_q = ctx.Queue()

        child = ctx.Process(
            target=_lock_worker_process,
            args=(str(self.service.lock_file), cmd_q, resp_q),
        )
        child.start()

        try:
            # 1. Parent acquires lock
            parent_lock = VectorStoreLock(self.service.lock_file, timeout_seconds=0.0)
            parent_lock.acquire()

            # 2. Child attempts to acquire while parent holds it -> Must fail with CONFLICT
            cmd_q.put("ACQUIRE")
            status, err = resp_q.get(timeout=12.0)
            self.assertEqual(status, "CONFLICT", f"Child should have encountered lock conflict: {err}")

            # 3. Parent releases lock
            parent_lock.release()

            # 4. Child attempts to acquire again -> Must succeed
            cmd_q.put("ACQUIRE")
            status, err = resp_q.get(timeout=12.0)
            self.assertEqual(status, "ACQUIRED", f"Child should have acquired lock: {err}")

            # 5. Parent attempts to acquire while child holds it -> Must fail with VectorStoreLockConflictError
            with self.assertRaises(VectorStoreLockConflictError):
                parent_lock.acquire()

            # 6. Child releases lock
            cmd_q.put("RELEASE")
            status, err = resp_q.get(timeout=12.0)
            self.assertEqual(status, "RELEASED", f"Child should have released lock: {err}")

            # 7. Parent acquires successfully after child release
            parent_lock.acquire()
            parent_lock.release()

        finally:
            cmd_q.put("STOP")
            child.join(timeout=3.0)
            if child.is_alive():
                child.terminate()

    def test_snapshot_immutability_contract(self):
        """Verify snapshot immutability contract prevents modification by external consumers."""
        from types import MappingProxyType

        index, metadata = self._create_sample_vectors_and_metadata(count=3)
        snap = self.service.commit_generation_bundle(index, metadata)

        # 1. Dict mappings are MappingProxyType and reject item assignment
        self.assertIsInstance(snap.int_to_chunk_id, MappingProxyType)
        with self.assertRaises(TypeError):
            snap.int_to_chunk_id[99] = "malicious_chunk"

        self.assertIsInstance(snap.chunk_id_to_int, MappingProxyType)
        with self.assertRaises(TypeError):
            snap.chunk_id_to_int["c_new"] = 100

        self.assertIsInstance(snap.chunk_metadata, MappingProxyType)
        with self.assertRaises(TypeError):
            snap.chunk_metadata["c_new"] = {}

        # Nested chunk metadata dicts are also immutable mapping proxies
        first_cid = list(snap.chunk_metadata.keys())[0]
        self.assertIsInstance(snap.chunk_metadata[first_cid], MappingProxyType)
        with self.assertRaises(TypeError):
            snap.chunk_metadata[first_cid]["text"] = "mutated text"

        # 2. Document chunk lists are immutable tuples
        self.assertIsInstance(snap.doc_id_to_chunk_ids, MappingProxyType)
        first_doc = list(snap.doc_id_to_chunk_ids.keys())[0]
        self.assertIsInstance(snap.doc_id_to_chunk_ids[first_doc], tuple)
        with self.assertRaises(AttributeError):
            snap.doc_id_to_chunk_ids[first_doc].append("extra_chunk")

        # 3. Direct attribute reassignment is blocked via __setattr__
        with self.assertRaises(AttributeError):
            snap.generation_id = "hacked_gen_id"

        with self.assertRaises(AttributeError):
            snap.directory = Path("/hacked")

        # 4. Helper lookup methods operate correctly
        faiss_id = snap.get_faiss_id(first_cid)
        self.assertIsNotNone(faiss_id)
        self.assertEqual(snap.get_chunk_id(faiss_id), first_cid)

        chunk_meta_copy = snap.get_chunk_metadata(first_cid)
        self.assertIsInstance(chunk_meta_copy, dict)
        chunk_meta_copy["text"] = "modified locally"
        # Original snapshot remains unmodified
        self.assertNotEqual(snap.chunk_metadata[first_cid].get("text"), "modified locally")

        doc_chunks = snap.get_doc_chunk_ids(first_doc)
        self.assertIsInstance(doc_chunks, tuple)
        self.assertIn(first_cid, doc_chunks)

        # 5. FAISS index immutability contract
        self.assertIsInstance(snap.index, ReadOnlyFAISSIndex)
        dummy_vec = np.zeros((1, 384), dtype=np.float32)
        with self.assertRaises(VectorStoreMutationError):
            snap.index.add(dummy_vec)
        with self.assertRaises(VectorStoreMutationError):
            snap.index.add_with_ids(dummy_vec, np.array([99]))
        with self.assertRaises(VectorStoreMutationError):
            snap.index.reset()
        with self.assertRaises(VectorStoreMutationError):
            snap.index.remove_ids(np.array([1]))
        with self.assertRaises(VectorStoreMutationError):
            snap.index.train(dummy_vec)

        # Attribute assignment on ReadOnlyFAISSIndex is blocked
        with self.assertRaises(AttributeError):
            snap.index.ntotal = 999

        # Direct attribute reassignment of index on snapshot is blocked
        with self.assertRaises(AttributeError):
            snap.index = "malicious_index"

        # Read-only search operations succeed
        D, I = snap.index.search(dummy_vec, 2)
        self.assertEqual(D.shape, (1, 2))
        self.assertEqual(I.shape, (1, 2))

        # Snapshot search helper succeeds
        D2, I2 = snap.search(dummy_vec, 2)
        np.testing.assert_array_equal(D, D2)
        np.testing.assert_array_equal(I, I2)

    def test_load_generation_dimension_validation(self):
        """Verify load_generation rejects index or manifest dimension mismatch."""
        from backend.app.core.config import settings

        # Create valid generation
        index, metadata = self._create_sample_vectors_and_metadata(count=2)
        snap = self.service.commit_generation_bundle(index, metadata)

        # 1. Modify index file with mismatched dimension (e.g. 128 instead of 384)
        mismatched_index = faiss.IndexIDMap2(faiss.IndexFlatIP(128))
        faiss.write_index(mismatched_index, str(snap.directory / "index.faiss"))
        new_sha = compute_file_sha256(snap.directory / "index.faiss")

        # Update manifest hash to pass checksum check so dimension check fires
        manifest_p = snap.directory / "manifest.json"
        with open(manifest_p, "r", encoding="utf-8") as f:
            m = json.load(f)
        m["index_sha256"] = new_sha
        m["total_vectors"] = 0
        with open(manifest_p, "w", encoding="utf-8") as f:
            json.dump(m, f)

        with self.assertRaises(VectorStoreCorruptionError) as ctx:
            self.service.load_generation(snap.generation_id)
        self.assertIn("Index dimension mismatch", str(ctx.exception))

        # 2. Modify manifest declared dimension
        index2, metadata2 = self._create_sample_vectors_and_metadata(count=2)
        snap2 = self.service.commit_generation_bundle(index2, metadata2)
        manifest2_p = snap2.directory / "manifest.json"
        with open(manifest2_p, "r", encoding="utf-8") as f:
            m2 = json.load(f)
        m2["dimension"] = 512
        with open(manifest2_p, "w", encoding="utf-8") as f:
            json.dump(m2, f)

        with self.assertRaises(VectorStoreCorruptionError) as ctx2:
            self.service.load_generation(snap2.generation_id)
        self.assertIn("Manifest dimension mismatch", str(ctx2.exception))

    def test_load_generation_count_validation(self):
        """Verify load_generation detects vector, chunk, and document count discrepancies."""
        index, metadata = self._create_sample_vectors_and_metadata(count=4)
        snap = self.service.commit_generation_bundle(index, metadata)
        manifest_p = snap.directory / "manifest.json"

        # 1. Tamper with total_vectors
        with open(manifest_p, "r", encoding="utf-8") as f:
            m = json.load(f)
        m["total_vectors"] = 999
        with open(manifest_p, "w", encoding="utf-8") as f:
            json.dump(m, f)

        with self.assertRaises(VectorStoreCorruptionError) as ctx:
            self.service.load_generation(snap.generation_id)
        self.assertIn("Vector count mismatch", str(ctx.exception))

        # 2. Tamper with total_chunks
        m["total_vectors"] = 4
        m["total_chunks"] = 999
        with open(manifest_p, "w", encoding="utf-8") as f:
            json.dump(m, f)

        with self.assertRaises(VectorStoreCorruptionError) as ctx2:
            self.service.load_generation(snap.generation_id)
        self.assertIn("Chunk count mismatch", str(ctx2.exception))

        # 3. Tamper with total_documents
        m["total_chunks"] = 4
        m["total_documents"] = 999
        with open(manifest_p, "w", encoding="utf-8") as f:
            json.dump(m, f)

        with self.assertRaises(VectorStoreCorruptionError) as ctx3:
            self.service.load_generation(snap.generation_id)
        self.assertIn("Document count mismatch", str(ctx3.exception))

    def test_load_generation_id_mapping_and_coherence_validation(self):
        """Verify load_generation validates ID mapping uniqueness, bijectivity, and metadata coherence."""
        # 1. ID mapping count mismatch
        index1, metadata1 = self._create_sample_vectors_and_metadata(count=3)
        # Drop one entry from int_to_chunk_id (keys are integers 1, 2, 3)
        metadata1["int_to_chunk_id"].pop(1)
        with self.assertRaises(VectorStoreCorruptionError) as ctx1:
            self.service.commit_generation_bundle(index1, metadata1)
        self.assertIn("int_to_chunk_id mapping size", str(ctx1.exception))

        # 2. Inconsistent bidirectional mapping (same size 3, unique values, but bijection fails)
        index2, metadata2 = self._create_sample_vectors_and_metadata(count=3)
        cids = list(metadata2["chunk_id_to_int"].keys())
        # Swap the mapped FAISS IDs between chunk 0 and chunk 1
        metadata2["chunk_id_to_int"][cids[0]] = 2
        metadata2["chunk_id_to_int"][cids[1]] = 1
        with self.assertRaises(VectorStoreCorruptionError) as ctx2:
            self.service.commit_generation_bundle(index2, metadata2)
        self.assertIn("Inconsistent bidirectional ID mapping", str(ctx2.exception))

        # 3. next_id boundary failure (next_id <= max_id)
        index3, metadata3 = self._create_sample_vectors_and_metadata(count=3)
        metadata3["next_id"] = 2  # max ID is 3, so next_id=2 violates boundary
        with self.assertRaises(VectorStoreCorruptionError) as ctx3:
            self.service.commit_generation_bundle(index3, metadata3)
        self.assertIn("must be strictly greater than maximum allocated FAISS ID", str(ctx3.exception))

        # 4. Chunk catalog mismatch (chunk_metadata keys != chunk_id_to_int keys)
        index4, metadata4 = self._create_sample_vectors_and_metadata(count=3)
        metadata4["chunk_metadata"]["orphan_chunk"] = {"doc_id": "doc_test", "text": "orphan"}
        with self.assertRaises(VectorStoreCorruptionError) as ctx4:
            self.service.commit_generation_bundle(index4, metadata4)
        self.assertIn("Chunk catalog mismatch", str(ctx4.exception))

        # 5. Non-disjoint or invalid doc chunk mapping
        index5, metadata5 = self._create_sample_vectors_and_metadata(count=3)
        cid = list(metadata5["chunk_metadata"].keys())[0]
        metadata5["doc_id_to_chunk_ids"]["second_doc"] = [cid]  # duplicate cid across docs
        with self.assertRaises(VectorStoreCorruptionError) as ctx5:
            self.service.commit_generation_bundle(index5, metadata5)
        self.assertIn("Duplicate chunk IDs found across document entries", str(ctx5.exception))

        # 6. Chunk metadata references invalid doc_id
        index6, metadata6 = self._create_sample_vectors_and_metadata(count=3)
        first_cid = list(metadata6["chunk_metadata"].keys())[0]
        metadata6["chunk_metadata"][first_cid]["doc_id"] = "nonexistent_doc"
        with self.assertRaises(VectorStoreCorruptionError) as ctx6:
            self.service.commit_generation_bundle(index6, metadata6)
        self.assertIn("references missing or uncataloged doc_id", str(ctx6.exception))

    def test_prune_historical_generations_lock_safety_and_parent_protection(self):
        """Verify generation pruning respects active generation, rollback parent, and lock safety."""
        # Create 4 generations: g1 -> g2 -> g3 -> g4
        idx1, m1 = self._create_sample_vectors_and_metadata(count=1)
        snap1 = self.service.commit_generation_bundle(idx1, m1)

        idx2, m2 = self._create_sample_vectors_and_metadata(count=1)
        snap2 = self.service.commit_generation_bundle(idx2, m2, parent_generation_id=snap1.generation_id)

        idx3, m3 = self._create_sample_vectors_and_metadata(count=1)
        snap3 = self.service.commit_generation_bundle(idx3, m3, parent_generation_id=snap2.generation_id)

        idx4, m4 = self._create_sample_vectors_and_metadata(count=1)
        snap4 = self.service.commit_generation_bundle(idx4, m4, parent_generation_id=snap3.generation_id)

        # Active generation is snap4, parent is snap3
        self.assertEqual(self.service.active_generation_id, snap4.generation_id)

        # 1. Pruning with keep_count=1 and grace_period=0:
        # snap4 (active) and snap3 (rollback parent) MUST NOT be pruned!
        pruned = self.service.prune_historical_generations(keep_count=1, grace_period_seconds=0.0)

        # Verify snap4 and snap3 directories still exist
        self.assertTrue(snap4.directory.exists(), "Active generation must not be pruned")
        self.assertTrue(snap3.directory.exists(), "Parent rollback generation must not be pruned")

        # Older unreferenced generations outside keep_count (e.g. snap1) can be pruned
        self.assertIn(snap1.generation_id, pruned)
        self.assertFalse(snap1.directory.exists())

        # 2. Lock contention test: When process lock is held, pruning defers without raising
        external_lock = VectorStoreLock(self.service.lock_file, timeout_seconds=0.0)
        external_lock.acquire()
        try:
            # prune should return empty list gracefully without error
            deferred_pruned = self.service.prune_historical_generations(keep_count=1, grace_period_seconds=0.0)
            self.assertEqual(deferred_pruned, [])
        finally:
            external_lock.release()

    def test_reader_isolation_context_manager(self):
        """Verify readers hold an immutable in-memory view while writers commit new generations."""
        index1, meta1 = self._create_sample_vectors_and_metadata(count=3)
        snap1 = self.service.commit_generation_bundle(index1, meta1)

        # Reader checks out snapshot
        with self.service.acquire_snapshot() as reader_snap:
            self.assertEqual(reader_snap.generation_id, snap1.generation_id)
            self.assertEqual(reader_snap.active_readers, 1)

            # Writer commits a new generation bundle in parallel
            index2, meta2 = self._create_sample_vectors_and_metadata(count=8)
            snap2 = self.service.commit_generation_bundle(index2, meta2)

            # Active generation in service changed
            self.assertEqual(self.service.active_generation_id, snap2.generation_id)

            # But the active reader's snapshot reference is completely undisturbed
            self.assertEqual(reader_snap.generation_id, snap1.generation_id)
            self.assertEqual(reader_snap.total_vectors, 3)

        # After exiting context manager, reader count decreases
        self.assertEqual(snap1.active_readers, 0)

    def test_clear_index_resets_to_empty_generation(self):
        """Verify clear_index generates a new empty generation without file system corruption."""
        index, meta = self._create_sample_vectors_and_metadata(count=5)
        self.service.commit_generation_bundle(index, meta)
        self.assertEqual(self.service.total_vectors, 5)

        res = self.service.clear_index()
        self.assertEqual(res["status"], "CLEARED")
        self.assertEqual(self.service.total_vectors, 0)
        self.assertEqual(self.service.total_chunks, 0)
        self.assertEqual(self.service.total_documents, 0)
        self.assertTrue(self.service.is_ready)

    def test_fsync_dir_error_handling_and_logging(self):
        """Verify fsync_dir handles POSIX directory sync errors without silent failure."""
        if os.name != "nt":
            # On POSIX, a non-existent directory descriptor should raise or log
            fake_dir = Path(self.test_dir) / "non_existent_subdir"
            result = fsync_dir(fake_dir, raise_on_failure=False)
            self.assertFalse(result)

            with self.assertRaises(OSError):
                fsync_dir(fake_dir, raise_on_failure=True)
        else:
            # On Windows, fsync_dir is documented as a successful no-op
            result = fsync_dir(Path(self.test_dir), raise_on_failure=True)
            self.assertTrue(result)

    def test_initial_startup_creates_empty_generation(self):
        """Verify that running startup recovery on an uninitialized directory creates gen 0."""
        fresh_dir = tempfile.mkdtemp(prefix="unimind_fresh_")
        try:
            fresh_service = VectorStoreService(index_dir=fresh_dir)
            snap = fresh_service.startup_recovery()
            self.assertEqual(snap.total_vectors, 0)
            self.assertTrue(fresh_service.is_ready)
            self.assertTrue(fresh_service.pointer_file.exists())
        finally:
            shutil.rmtree(fresh_dir, ignore_errors=True)

    def test_automatic_pruning_runs_post_commit_with_cross_process_safety(self):
        """Verify automatic generation pruning runs post-commit outside the commit lock and respects concurrency."""
        # Initialize service configured to retain only 2 generations with immediate pruning eligibility
        service = VectorStoreService(
            index_dir=self.test_dir,
            retention_keep_count=2,
            retention_grace_period_seconds=0.0,
        )

        # Commit 4 sequential generations: g1 -> g2 -> g3 -> g4
        idx1, m1 = self._create_sample_vectors_and_metadata(count=1)
        snap1 = service.commit_generation_bundle(idx1, m1)

        idx2, m2 = self._create_sample_vectors_and_metadata(count=1)
        snap2 = service.commit_generation_bundle(idx2, m2, parent_generation_id=snap1.generation_id)

        idx3, m3 = self._create_sample_vectors_and_metadata(count=1)
        snap3 = service.commit_generation_bundle(idx3, m3, parent_generation_id=snap2.generation_id)

        idx4, m4 = self._create_sample_vectors_and_metadata(count=1)
        snap4 = service.commit_generation_bundle(idx4, m4, parent_generation_id=snap3.generation_id)

        # After commit 4:
        # snap4 is active (protected)
        # snap3 is parent of active (protected)
        # Older generation snap1 outside keep_count=2 must have been automatically pruned
        self.assertTrue(snap4.directory.exists(), "Active generation snap4 must be preserved")
        self.assertTrue(snap3.directory.exists(), "Rollback parent generation snap3 must be preserved")
        self.assertFalse(snap1.directory.exists(), "Historical generation snap1 must be automatically pruned")

        # Concurrency safety: If pruning encounters lock contention, commit still succeeds completely
        with patch.object(service, "prune_historical_generations", side_effect=VectorStoreLockConflictError("Simulated lock conflict")):
            idx5, m5 = self._create_sample_vectors_and_metadata(count=1)
            snap5 = service.commit_generation_bundle(idx5, m5, parent_generation_id=snap4.generation_id)
            self.assertEqual(service.active_generation_id, snap5.generation_id)

    def test_fsync_dir_failure_after_os_replace_updates_in_memory_snapshot(self):
        """Verify fsync_dir failure after os.replace updates in-memory snapshot and prevents stale reads."""
        # 1. Commit initial generation 1
        idx1, m1 = self._create_sample_vectors_and_metadata(count=2)
        snap1 = self.service.commit_generation_bundle(idx1, m1)
        self.assertEqual(self.service.active_generation_id, snap1.generation_id)

        # 2. Commit generation 2 with fault-injected fsync_dir failure after os.replace
        idx2, m2 = self._create_sample_vectors_and_metadata(count=4)

        original_fsync_dir = fsync_dir

        def fault_injected_fsync_dir(path, raise_on_failure=False):
            # Fail only when called for the index root directory (post os.replace sync)
            if Path(path) == Path(self.test_dir):
                if raise_on_failure:
                    raise OSError("Simulated physical storage controller synchronization failure")
                return False
            return original_fsync_dir(path, raise_on_failure)

        with patch("backend.app.rag.vector_store.fsync_dir", side_effect=fault_injected_fsync_dir):
            with self.assertRaises(VectorStoreError) as ctx:
                self.service.commit_generation_bundle(idx2, m2, parent_generation_id=snap1.generation_id)
            self.assertIn("directory fsync failed", str(ctx.exception))

        # 3. Verify in-memory state is synchronized with the new generation (NOT silently retaining Gen 1!)
        self.assertNotEqual(self.service.active_generation_id, snap1.generation_id)
        self.assertEqual(self.service.total_vectors, 4)
        self.assertIn("Directory fsync failed after pointer switch", self.service._last_error)

        # 4. Verify on-disk pointer matches in-memory state (coherent, not split-brain)
        with open(self.service.pointer_file, "r", encoding="utf-8") as f:
            pointer_data = json.load(f)
        self.assertEqual(pointer_data["active_generation_id"], self.service.active_generation_id)

        # 5. Verify reader acquires the active new generation
        with self.service.acquire_snapshot() as reader_snap:
            self.assertEqual(reader_snap.total_vectors, 4)
            self.assertEqual(reader_snap.generation_id, self.service.active_generation_id)

    def test_snapshot_faiss_index_read_only_contract_and_reader_isolation(self):
        """Verify FAISS index in GenerationSnapshot blocks mutation methods while readers query safely."""
        idx, meta = self._create_sample_vectors_and_metadata(count=3)
        snap = self.service.commit_generation_bundle(idx, meta)

        # 1. Type validation
        self.assertIsInstance(snap.index, ReadOnlyFAISSIndex)
        self.assertEqual(snap.index.ntotal, 3)
        self.assertEqual(snap.index.d, 384)

        # 2. Mutation operations strictly forbidden
        dummy = np.random.randn(1, 384).astype(np.float32)
        faiss.normalize_L2(dummy)

        for method_name in ("add", "add_with_ids", "reset", "remove_ids", "train", "merge_from"):
            with self.subTest(method=method_name):
                fn = getattr(snap.index, method_name)
                with self.assertRaises(VectorStoreMutationError):
                    if method_name in ("add", "train"):
                        fn(dummy)
                    elif method_name == "add_with_ids":
                        fn(dummy, np.array([99], dtype=np.int64))
                    elif method_name == "remove_ids":
                        fn(np.array([1], dtype=np.int64))
                    else:
                        fn()

        # 3. Attribute assignment blocked
        with self.assertRaises(AttributeError):
            snap.index.d = 512

        # 4. Reader isolation: reader performs queries before, during, and after attempted mutations
        with self.service.acquire_snapshot() as reader_snap:
            D1, I1 = reader_snap.search(dummy, top_k=2)
            self.assertEqual(D1.shape, (1, 2))
            self.assertEqual(I1.shape, (1, 2))

            # Attempt a mutation inside reader scope
            with self.assertRaises(VectorStoreMutationError):
                reader_snap.index.add(dummy)

            # Query results remain completely identical and unpolluted
            D2, I2 = reader_snap.search(dummy, top_k=2)
            np.testing.assert_array_equal(D1, D2)
            np.testing.assert_array_equal(I1, I2)


if __name__ == "__main__":
    unittest.main()
