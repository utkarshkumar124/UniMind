"""Test suite verifying FastAPI service skeleton, health, and readiness endpoints."""

import unittest
from fastapi.testclient import TestClient
from backend.app.main import app


class TestHealthEndpoints(unittest.TestCase):
    """Unit tests for root, health, and readiness check API endpoints."""

    @classmethod
    def setUpClass(cls):
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_root_endpoint(self):
        """Test the root endpoint returns 200 and expected status information."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "online")
        self.assertIn("UniMind", data["service"])
        self.assertEqual(data["docs_url"], "/docs")
        self.assertEqual(data["health_url"], "/health")
        self.assertEqual(data["api_v1_url"], "/api/v1")

    def test_root_health_check(self):
        """Test top-level /health endpoint returns healthy status and READY embedding state."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["embedding_status"], "READY")
        self.assertIn("version", data)
        self.assertIn("environment", data)

    def test_api_v1_health_check(self):
        """Test versioned /api/v1/health endpoint returns healthy status and READY embedding state."""
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["embedding_status"], "READY")
        self.assertIn("version", data)

    def test_readiness_endpoints(self):
        """Test /ready and /api/v1/ready return 200 when embedding model is READY."""
        r1 = self.client.get("/ready")
        r2 = self.client.get("/api/v1/ready")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json(), r2.json())

    def test_health_endpoints_consistency(self):
        """Verify that root /health and /api/v1/health return identical payloads."""
        root_resp = self.client.get("/health")
        v1_resp = self.client.get("/api/v1/health")
        self.assertEqual(root_resp.status_code, 200)
        self.assertEqual(v1_resp.status_code, 200)
        self.assertEqual(root_resp.json(), v1_resp.json())


if __name__ == "__main__":
    unittest.main()
