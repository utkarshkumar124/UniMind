"""Test suite verifying FastAPI service skeleton and health endpoints."""

import unittest
from fastapi.testclient import TestClient
from backend.app.main import app


class TestHealthEndpoints(unittest.TestCase):
    """Unit tests for root and health check API endpoints."""

    def setUp(self):
        self.client = TestClient(app)

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
        """Test top-level /health endpoint returns healthy status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("version", data)
        self.assertIn("environment", data)

    def test_api_v1_health_check(self):
        """Test versioned /api/v1/health endpoint returns healthy status."""
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("version", data)

    def test_health_endpoints_consistency(self):
        """Verify that root /health and /api/v1/health return identical payloads."""
        root_resp = self.client.get("/health")
        v1_resp = self.client.get("/api/v1/health")
        self.assertEqual(root_resp.status_code, 200)
        self.assertEqual(v1_resp.status_code, 200)
        self.assertEqual(root_resp.json(), v1_resp.json())


if __name__ == "__main__":
    unittest.main()
