"""Tests for startup embedding model initialization, warmup, concurrency, and failure states."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.rag.embedder import (
    EmbeddingModelManager,
    MockEmbeddingModel,
    ModelInitializationError,
    EMBEDDING_STATE_INITIALIZING,
    EMBEDDING_STATE_READY,
    EMBEDDING_STATE_FAILED,
    get_default_embedder,
    reset_default_embedder,
)


class _CountingMockModel(MockEmbeddingModel):
    """Spy model tracking encode calls (warmup vs query inference)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.encode_calls = []

    def encode(self, sentences, **kwargs):
        self.encode_calls.append(sentences)
        return super().encode(sentences, **kwargs)


class TestEmbedderStartupAndLifecycle(unittest.TestCase):
    """Verify startup loading, warmup, singleton reuse, thread safety, and failure handling."""

    def setUp(self):
        reset_default_embedder()

    def tearDown(self):
        reset_default_embedder()

    def test_startup_loads_and_warms_up_model_once(self):
        """FastAPI lifespan initializes and warms up the model once; queries reuse it."""
        created_models = []

        def fake_loader(self_mgr, target_name):
            m = _CountingMockModel(dimension=384)
            created_models.append(m)
            return m

        with patch.object(EmbeddingModelManager, "_load_sentence_transformer", fake_loader):
            with TestClient(app) as client:
                manager = EmbeddingModelManager()
                self.assertEqual(len(created_models), 1)
                self.assertEqual(manager.status, EMBEDDING_STATE_READY)
                self.assertIsNotNone(manager.timings["load_ms"])
                self.assertIsNotNone(manager.timings["warmup_ms"])
                # Warmup call executed during startup
                self.assertEqual(created_models[0].encode_calls, ["query: warmup"])

                # Health & readiness reflect READY
                h = client.get("/api/v1/health").json()
                self.assertEqual(h["status"], "healthy")
                self.assertEqual(h["embedding_status"], EMBEDDING_STATE_READY)
                self.assertEqual(client.get("/api/v1/ready").status_code, 200)

                # First & subsequent queries reuse the same singleton model
                e1 = get_default_embedder()
                e2 = get_default_embedder()
                self.assertIs(e1, e2)
                self.assertIs(e1.model, created_models[0])
                e1.encode_query("attendance requirement")
                e2.encode_query("exam rules")
                self.assertEqual(len(created_models), 1)

    def test_concurrent_requests_never_duplicate_model_load(self):
        """Multiple threads calling get_default_embedder concurrently trigger exactly one load."""
        load_count = 0

        def slow_fake_loader(self_mgr, target_name):
            nonlocal load_count
            import time
            time.sleep(0.05)
            load_count += 1
            return MockEmbeddingModel(dimension=384)

        with patch.object(EmbeddingModelManager, "_load_sentence_transformer", slow_fake_loader):
            def worker(_idx):
                emb = get_default_embedder()
                return emb.encode_query("concurrent query")

            with ThreadPoolExecutor(max_workers=8) as pool:
                vecs = list(pool.map(worker, range(8)))

            self.assertEqual(len(vecs), 8)
            self.assertEqual(load_count, 1)
            self.assertEqual(EmbeddingModelManager().status, EMBEDDING_STATE_READY)

    def test_startup_failure_sets_failed_and_does_not_retry_per_query(self):
        """If startup loading fails, health/ready/query report failure without reloading per query."""
        attempts = 0

        def failing_loader(self_mgr, target_name):
            nonlocal attempts
            attempts += 1
            raise RuntimeError("Corrupted model cache")

        with patch.object(EmbeddingModelManager, "_load_sentence_transformer", failing_loader):
            with TestClient(app) as client:
                manager = EmbeddingModelManager()
                self.assertEqual(attempts, 1)
                self.assertEqual(manager.status, EMBEDDING_STATE_FAILED)
                self.assertIn("Corrupted model cache", manager.error)

                # Health reports unhealthy + FAILED; readiness returns 503
                health_resp = client.get("/api/v1/health")
                self.assertEqual(health_resp.status_code, 200)
                h_data = health_resp.json()
                self.assertEqual(h_data["status"], "unhealthy")
                self.assertEqual(h_data["embedding_status"], EMBEDDING_STATE_FAILED)
                self.assertEqual(client.get("/api/v1/ready").status_code, 503)

                # Queries return 503 and do NOT trigger reload attempts
                q1 = client.post("/api/v1/query", json={"query": "test"})
                q2 = client.post("/api/v1/chat", json={"prompt": "test"})
                self.assertEqual(q1.status_code, 503)
                self.assertEqual(q2.status_code, 503)
                self.assertEqual(attempts, 1)

                # Direct embedder access also fails fast without retrying
                with self.assertRaises(ModelInitializationError):
                    get_default_embedder()
                self.assertEqual(attempts, 1)

    def test_initial_uninitialized_state_before_startup(self):
        """Fresh manager starts in INITIALIZING state and readiness returns 503 before startup."""
        manager = EmbeddingModelManager()
        self.assertEqual(manager.status, EMBEDDING_STATE_INITIALIZING)
        raw_client = TestClient(app)
        h = raw_client.get("/api/v1/health").json()
        self.assertEqual(h["status"], "initializing")
        self.assertEqual(h["embedding_status"], EMBEDDING_STATE_INITIALIZING)
        self.assertEqual(raw_client.get("/api/v1/ready").status_code, 503)


if __name__ == "__main__":
    unittest.main()
