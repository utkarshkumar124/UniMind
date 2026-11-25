"""Tests for Sign In, Register, Forgot Password, Reset Password, and Session routes."""

import os
import tempfile
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes import auth as auth_route
from backend.app.services.auth_service import AuthService

test_app = FastAPI()
test_app.include_router(auth_route.router, prefix="/api/v1")


class TestAuthAPI(unittest.TestCase):
    """End-to-end tests for /api/v1/auth/* using an isolated temporary SQLite database."""

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="unimind_auth_test_")
        cls.db_path = os.path.join(cls.tmp_dir, "test_auth.db")
        cls.orig_service = auth_route.auth_service
        auth_route.auth_service = AuthService(db_path=cls.db_path)
        cls.client = TestClient(test_app)

    @classmethod
    def tearDownClass(cls):
        auth_route.auth_service = cls.orig_service

    def test_register_login_forgot_reset_and_logout_flow(self):
        # 1. Register new student
        reg = self.client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Aarav Sharma",
                "email": "aarav@lpu.in",
                "password": "password123",
                "registration_no": "12304567",
            },
        )
        self.assertEqual(reg.status_code, 201)
        reg_data = reg.json()
        self.assertEqual(reg_data["user"]["email"], "aarav@lpu.in")
        self.assertEqual(reg_data["user"]["full_name"], "Aarav Sharma")
        self.assertTrue(reg_data["access_token"])

        # 2. Duplicate registration rejected with 409
        dup = self.client.post(
            "/api/v1/auth/register",
            json={"full_name": "Duplicate", "email": "aarav@lpu.in", "password": "password123"},
        )
        self.assertEqual(dup.status_code, 409)

        # 3. Verify /me works with bearer token
        me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {reg_data['access_token']}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["registration_no"], "12304567")

        # 4. Wrong password rejected with 401
        bad_login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "aarav@lpu.in", "password": "wrongpassword"},
        )
        self.assertEqual(bad_login.status_code, 401)

        # 5. Forgot password issues 6-digit code
        forgot = self.client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "aarav@lpu.in"},
        )
        self.assertEqual(forgot.status_code, 200)
        otp = forgot.json()["dev_reset_code"]
        self.assertEqual(len(otp), 6)

        # 6. Reset password updates credentials and invalidates old token
        reset = self.client.post(
            "/api/v1/auth/reset-password",
            json={"email": "aarav@lpu.in", "reset_code": otp, "new_password": "newsecret99"},
        )
        self.assertEqual(reset.status_code, 200)

        old_me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {reg_data['access_token']}"},
        )
        self.assertEqual(old_me.status_code, 401)

        # 7. Login with new password & logout
        login2 = self.client.post(
            "/api/v1/auth/login",
            json={"email": "aarav@lpu.in", "password": "newsecret99"},
        )
        self.assertEqual(login2.status_code, 200)
        new_tok = login2.json()["access_token"]

        logout = self.client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {new_tok}"},
        )
        self.assertEqual(logout.status_code, 200)
        after_logout = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_tok}"},
        )
        self.assertEqual(after_logout.status_code, 401)


if __name__ == "__main__":
    unittest.main()
