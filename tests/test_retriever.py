"""Tests for Phase 4 Milestone 2 Semantic Retriever engine."""

import os
import shutil
import tempfile
import unittest
import numpy as np
import faiss

from backend.app.rag.embedder import DenseEmbedder, MockEmbeddingModel
from backend.app.rag.vector_store import (
    VectorStoreService,
    VectorStoreNotReadyError,
)
from backend.app.rag.retriever import (
    SemanticRetriever,
    RetrievedChunk,
    RetrievalResult,
    RetrieverError,
    RetrieverNotReadyError,
)


class TestSemanticRetriever(unittest.TestCase):
    """Test suite for semantic vector retrieval engine."""

    def setUp(self):
        """Set up an isolated temporary directory, mock embedder, and vector store."""
        self.test_dir = tempfile.mkdtemp(prefix="unimind_retriever_test_")
        self.vector_store = VectorStoreService(index_dir=self.test_dir)
        self.vector_store.startup_recovery()
        self.embedder = DenseEmbedder(use_mock=True)
        self.retriever = SemanticRetriever(
            vector_store=self.vector_store,
            embedder=self.embedder,
            default_top_k=3,
        )

    def tearDown(self):
        """Clean up the temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _seed_test_generation(self, count: int = 6, dim: int = 384):
        """Helper to create and commit a test generation with structured metadata."""
        flat_index = faiss.IndexFlatIP(dim)
        index = faiss.IndexIDMap2(flat_index)

        # Generate vectors from predictable text using the mock embedder
        passages = [
            "Attendance policy requires a minimum of 75 percent attendance to sit for examinations.",
            "Hostel curfew is strictly 9:30 PM on weekdays and 10:00 PM on weekends.",
            "Fee refund applications must be submitted within 15 days of admission cancellation.",
            "Continuous assessment marks include quizzes, assignments, and mid-term evaluations.",
            "Hostel room changes are permitted only during the first two weeks of the semester.",
            "Examination re-evaluation requests can be filed within 7 days of grade announcement.",
        ]

        # Use actual passage encoding
        vecs = self.embedder.encode_passages(passages[:count])
        ids = np.arange(1, count + 1, dtype=np.int64)
        index.add_with_ids(vecs, ids)

        int_to_chunk_id = {}
        chunk_id_to_int = {}
        chunk_metadata = {}
        doc_chunks = {}

        departments = ["Academics", "Student Affairs", "Finance", "Academics", "Student Affairs", "Examinations"]
        categories = ["Policy", "Hostel", "Fee", "Evaluation", "Hostel", "Rules"]

        for idx, (p_text, faiss_id) in enumerate(zip(passages[:count], ids)):
            doc_id = f"doc_{departments[idx].lower().replace(' ', '_')}"
            cid = f"{doc_id}#p1#c{idx}"
            int_to_chunk_id[int(faiss_id)] = cid
            chunk_id_to_int[cid] = int(faiss_id)

            if doc_id not in doc_chunks:
                doc_chunks[doc_id] = []
            doc_chunks[doc_id].append(cid)

            chunk_metadata[cid] = {
                "text": p_text,
                "doc_id": doc_id,
                "filename": f"{doc_id}.pdf",
                "page_start": 1,
                "page_end": 1,
                "chunk_index": idx,
                "department": departments[idx],
                "category": categories[idx],
            }

        metadata = {
            "int_to_chunk_id": int_to_chunk_id,
            "chunk_id_to_int": chunk_id_to_int,
            "doc_id_to_chunk_ids": doc_chunks,
            "chunk_metadata": chunk_metadata,
            "next_id": count + 1,
        }

        return self.vector_store.commit_generation_bundle(index, metadata)

    def test_empty_index_returns_empty_result_cleanly(self):
        """Verify querying an empty vector store returns an empty result without error."""
        res = self.retriever.retrieve("What is the attendance policy?")
        self.assertIsInstance(res, RetrievalResult)
        self.assertEqual(len(res.chunks), 0)
        self.assertEqual(res.total_found, 0)
        self.assertGreaterEqual(res.latency_ms, 0.0)

    def test_successful_semantic_retrieval(self):
        """Verify successful semantic retrieval ranks relevant chunks with valid provenance."""
        self._seed_test_generation(count=6)

        query = "What is the minimum attendance requirement?"
        res = self.retriever.retrieve(query, top_k=3)

        self.assertIsInstance(res, RetrievalResult)
        self.assertEqual(res.query, query)
        self.assertLessEqual(len(res.chunks), 3)
        self.assertGreater(len(res.chunks), 0)
        self.assertGreaterEqual(res.latency_ms, 0.0)

        top_chunk = res.chunks[0]
        self.assertIsInstance(top_chunk, RetrievedChunk)
        self.assertTrue(len(top_chunk.text) > 0)
        self.assertTrue(len(top_chunk.doc_id) > 0)
        self.assertTrue(len(top_chunk.chunk_id) > 0)
        self.assertIsInstance(top_chunk.score, float)
        self.assertGreaterEqual(top_chunk.page_start, 1)

    def test_top_k_parameter_enforcement(self):
        """Verify configurable top_k limits the number of returned chunks accurately."""
        self._seed_test_generation(count=6)

        for k in (1, 2, 4):
            res = self.retriever.retrieve("rules and regulations", top_k=k)
            self.assertEqual(len(res.chunks), k)
            self.assertEqual(res.total_found, k)

    def test_department_metadata_filtering(self):
        """Verify department metadata filter restricts results to specified department only."""
        self._seed_test_generation(count=6)

        res = self.retriever.retrieve("guidelines and timings", department="Student Affairs", top_k=5)
        self.assertGreater(len(res.chunks), 0)
        for chunk in res.chunks:
            self.assertEqual(chunk.department, "Student Affairs")

    def test_category_metadata_filtering(self):
        """Verify category metadata filter restricts results to specified category only."""
        self._seed_test_generation(count=6)

        res = self.retriever.retrieve("hostel curfew and rooms", category="Hostel", top_k=5)
        self.assertGreater(len(res.chunks), 0)
        for chunk in res.chunks:
            self.assertEqual(chunk.category, "Hostel")

    def test_similarity_threshold_filtering(self):
        """Verify min_similarity threshold discards chunks below the configured score."""
        self._seed_test_generation(count=6)

        # Baseline search to find actual scores
        base_res = self.retriever.retrieve("examination re-evaluation", top_k=5)
        self.assertGreater(len(base_res.chunks), 0)
        top_score = base_res.chunks[0].score

        # Set threshold higher than top score -> returns 0 results
        high_res = self.retriever.retrieve("examination re-evaluation", min_similarity=top_score + 0.1)
        self.assertEqual(len(high_res.chunks), 0)

        # Set threshold slightly lower than top score -> returns matching results
        filtered_res = self.retriever.retrieve("examination re-evaluation", min_similarity=top_score - 0.05)
        self.assertGreater(len(filtered_res.chunks), 0)
        for chunk in filtered_res.chunks:
            self.assertGreaterEqual(chunk.score, top_score - 0.05)

    def test_invalid_query_and_top_k_rejection(self):
        """Verify empty query strings and invalid top_k raise ValueError."""
        with self.assertRaises(ValueError):
            self.retriever.retrieve("")

        with self.assertRaises(ValueError):
            self.retriever.retrieve("   ")

        with self.assertRaises(ValueError):
            self.retriever.retrieve("valid query", top_k=0)

        with self.assertRaises(ValueError):
            self.retriever.retrieve("valid query", top_k=-5)

    def test_vector_store_not_ready_handling(self):
        """Verify RetrieverNotReadyError is raised when the vector store is in an unready state."""
        unready_service = VectorStoreService(index_dir=tempfile.mkdtemp(prefix="unready_vs_"))
        unready_service._state = "ERROR"
        unready_service._last_error = "Simulated disk storage failure"

        bad_retriever = SemanticRetriever(
            vector_store=unready_service,
            embedder=self.embedder,
        )

        with self.assertRaises(RetrieverNotReadyError):
            bad_retriever.retrieve("query text")

    def test_e5_query_prefix_behavior(self):
        """Verify that models with 'e5' in their name prepend 'query: ' during encoding."""
        # Check that DenseEmbedder for e5 sets query_prefix
        e5_embedder = DenseEmbedder(model_name="intfloat/multilingual-e5-small", use_mock=True)
        self.assertEqual(e5_embedder.query_prefix, "query: ")

        e5_retriever = SemanticRetriever(
            vector_store=self.vector_store,
            embedder=e5_embedder,
        )
        self._seed_test_generation(count=4)
        res = e5_retriever.retrieve("attendance policy", top_k=2)
        self.assertEqual(len(res.chunks), 2)

    def test_provenance_citation_metadata_completeness(self):
        """Verify retrieved chunks contain all required provenance for trustworthy citations."""
        self._seed_test_generation(count=6)

        res = self.retriever.retrieve("curfew", top_k=2)
        for chunk in res.chunks:
            self.assertIsNotNone(chunk.doc_id)
            self.assertIsNotNone(chunk.chunk_id)
            self.assertIsNotNone(chunk.text)
            self.assertIsNotNone(chunk.page_start)
            self.assertIsNotNone(chunk.department)
            self.assertIsNotNone(chunk.category)
            self.assertIn("filename", chunk.metadata)


if __name__ == "__main__":
    unittest.main()
