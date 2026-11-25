"""Tests for End-to-End Query and Chat API routes."""

import os
import shutil
import tempfile
import unittest
import numpy as np
import faiss
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.rag.vector_store import VectorStoreService, vector_store_service
from backend.app.rag.embedder import DenseEmbedder


class TestQueryAndChatAPI(unittest.TestCase):
    """Test suite for /api/v1/query and /api/v1/chat endpoints."""

    @classmethod
    def setUpClass(cls):
        """Set up test client and seed sample vector store data."""
        cls.client = TestClient(app)

        # Seed data in the active vector store
        flat_index = faiss.IndexFlatIP(384)
        index = faiss.IndexIDMap2(flat_index)
        embedder = DenseEmbedder(use_mock=True)

        passages = [
            "Students must maintain at least 75 percent attendance in every registered course.",
            "Hostel gates close at 9:30 PM on weekdays and 10:00 PM on weekends.",
            "Continuous assessment carries 40 percent weightage and end-term carries 60 percent.",
        ]

        vecs = embedder.encode_passages(passages)
        ids = np.array([1, 2, 3], dtype=np.int64)
        index.add_with_ids(vecs, ids)

        chunk_meta = {
            "doc_test#p1#c0": {
                "text": passages[0],
                "doc_id": "doc_test",
                "filename": "academic_regulations.pdf",
                "department": "Academic Affairs",
                "category": "Policy",
                "page_start": 4,
            },
            "doc_test#p1#c1": {
                "text": passages[1],
                "doc_id": "doc_test",
                "filename": "hostel_rules.pdf",
                "department": "Student Affairs",
                "category": "Hostel",
                "page_start": 2,
            },
            "doc_test#p1#c2": {
                "text": passages[2],
                "doc_id": "doc_test",
                "filename": "examination_scheme.pdf",
                "department": "Examinations",
                "category": "Grading",
                "page_start": 7,
            },
        }

        meta = {
            "int_to_chunk_id": {1: "doc_test#p1#c0", 2: "doc_test#p1#c1", 3: "doc_test#p1#c2"},
            "chunk_id_to_int": {"doc_test#p1#c0": 1, "doc_test#p1#c1": 2, "doc_test#p1#c2": 3},
            "doc_id_to_chunk_ids": {"doc_test": ["doc_test#p1#c0", "doc_test#p1#c1", "doc_test#p1#c2"]},
            "chunk_metadata": chunk_meta,
            "next_id": 4,
        }

        vector_store_service.commit_generation_bundle(index, meta)

    def test_query_endpoint_success(self):
        """Test POST /api/v1/query returns grounded answer and citations."""
        response = self.client.post(
            "/api/v1/query",
            json={"query": "What is the attendance requirement?", "top_k": 2},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answer", data)
        self.assertIn("sources", data)
        self.assertGreater(data["total_sources"], 0)
        self.assertGreaterEqual(data["latency_ms"], 0.0)

        # Check citation structure
        citation = data["sources"][0]
        self.assertEqual(citation["n"], 1)
        self.assertIn("doc_id", citation)
        self.assertIn("doc_title", citation)
        self.assertIn("page", citation)
        self.assertIn("quote", citation)

    def test_query_endpoint_empty_query_rejected(self):
        """Test POST /api/v1/query rejects empty strings with 422."""
        response = self.client.post(
            "/api/v1/query",
            json={"query": ""},
        )
        self.assertEqual(response.status_code, 422)

    def test_chat_endpoint_success(self):
        """Test POST /api/v1/chat returns content and sources matching frontend contract."""
        response = self.client.post(
            "/api/v1/chat",
            json={"prompt": "When do hostel gates close?"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("content", data)
        self.assertIn("sources", data)
        self.assertIsInstance(data["sources"], list)

        if data["sources"]:
            src = data["sources"][0]
            self.assertIn("n", src)
            self.assertIn("docId", src)
            self.assertIn("docTitle", src)
            self.assertIn("page", src)
            self.assertIn("quote", src)


if __name__ == "__main__":
    unittest.main()

