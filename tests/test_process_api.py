"""Integration tests for POST /api/v1/documents/{doc_id}/process endpoint."""

import os
import shutil
import tempfile
import unittest
import hashlib
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.services.document_service import document_service
from backend.app.services.embedding_service import embedding_service
from backend.app.rag.chunker import SimpleWhitespaceTokenizer, DocumentChunker
from backend.app.rag.embedder import DenseEmbedder
from tests.synthetic_pdf_generator import create_valid_multipage_pdf, create_empty_pdf


class TestProcessAPI(unittest.TestCase):
    """Test suite for the document chunking and embedding generation REST API."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="unimind_test_api_emb_")
        cls.raw_dir = os.path.join(cls.test_dir, "raw")
        cls.processed_dir = os.path.join(cls.test_dir, "processed")
        cls.db_path = os.path.join(cls.test_dir, "test_unimind.db")

        # Mock embedder and fast tokenizer for rapid endpoint testing
        cls.mock_embedder = DenseEmbedder(use_mock=True)
        cls.chunker = DocumentChunker(tokenizer=SimpleWhitespaceTokenizer(), target_chunk_size=100, chunk_overlap=20)

        # Reconfigure singletons to isolated temporary storage
        document_service.db_path = cls.db_path
        document_service.raw_dir = cls.raw_dir
        document_service.processed_dir = cls.processed_dir
        document_service._init_storage()

        embedding_service.db_path = cls.db_path
        embedding_service.raw_dir = cls.raw_dir
        embedding_service.processed_dir = cls.processed_dir
        embedding_service.chunker = cls.chunker
        embedding_service._embedder = cls.mock_embedder

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_process_nonexistent_document_returns_404(self):
        """Verify processing a nonexistent doc_id returns HTTP 404 Not Found."""
        res = self.client.post("/api/v1/documents/00000000-0000-0000-0000-000000000000/process")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json()["detail"].lower())

    def test_process_empty_document_returns_422(self):
        """Verify processing an empty document returns HTTP 422 Unprocessable Content."""
        empty_bytes = create_empty_pdf()
        upload_res = self.client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty_sample.pdf", empty_bytes, "application/pdf")},
            data={"department": "General", "category": "Empty"},
        )
        self.assertEqual(upload_res.status_code, 201)
        empty_doc_id = upload_res.json()["doc_id"]

        # Attempt to process empty document
        proc_res = self.client.post(f"/api/v1/documents/{empty_doc_id}/process")
        self.assertEqual(proc_res.status_code, 422)
        self.assertIn("empty", proc_res.json()["detail"].lower())

    def test_process_valid_document_success_lifecycle(self):
        """Verify successful document chunking, embedding generation, state verification, and deletion."""
        valid_bytes = create_valid_multipage_pdf()
        upload_res = self.client.post(
            "/api/v1/documents/upload",
            files={"file": ("academic_guidelines.pdf", valid_bytes, "application/pdf")},
            data={"department": "Academic Affairs", "category": "Policy"},
        )
        self.assertEqual(upload_res.status_code, 201)
        doc_id = upload_res.json()["doc_id"]

        # 1. Trigger processing
        proc_res = self.client.post(f"/api/v1/documents/{doc_id}/process")
        self.assertEqual(proc_res.status_code, 200)
        data = proc_res.json()

        self.assertEqual(data["doc_id"], doc_id)
        self.assertEqual(data["status"], "INDEXED")
        self.assertGreater(data["total_chunks"], 0)
        self.assertEqual(data["vector_dimension"], 384)
        self.assertTrue(data["embedding_file"].endswith("_embeddings.npy"))
        self.assertTrue(data["chunks_file"].endswith("_chunks.json"))
        self.assertGreater(data["processing_time_seconds"], 0)

        # 2. Check GET /documents/{doc_id} reflects INDEXED and total_chunks
        get_res = self.client.get(f"/api/v1/documents/{doc_id}")
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        self.assertEqual(get_data["status"], "INDEXED")
        self.assertEqual(get_data["total_chunks"], data["total_chunks"])

        # 3. Check duplicate processing without force returns 409 Conflict
        dup_res = self.client.post(f"/api/v1/documents/{doc_id}/process")
        self.assertEqual(dup_res.status_code, 409)

        # 4. Reprocessing with force=True returns 200
        force_res = self.client.post(f"/api/v1/documents/{doc_id}/process?force=true")
        self.assertEqual(force_res.status_code, 200)
        self.assertEqual(force_res.json()["status"], "INDEXED")

        # 5. Clean up via DELETE /documents/{doc_id}
        del_res = self.client.delete(f"/api/v1/documents/{doc_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["deleted"])

        # 6. Verify 404 after deletion
        get_after_del = self.client.get(f"/api/v1/documents/{doc_id}")
        self.assertEqual(get_after_del.status_code, 404)


if __name__ == "__main__":
    unittest.main()
