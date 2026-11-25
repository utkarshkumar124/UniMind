"""SQLite-backed authentication service for user registration, login, sessions, and password resets."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from backend.app.core.config import settings


class AuthError(Exception):
    """Base authentication exception."""


class EmailAlreadyExistsError(AuthError):
    """Raised when registering an email address that already exists."""


class InvalidCredentialsError(AuthError):
    """Raised when email/password login fails."""


class ResetCodeError(AuthError):
    """Raised when a password reset code is invalid, expired, or email is unknown."""


def _hash_password(password: str, salt_hex: Optional[str] = None) -> str:
    """Hash a password using scrypt with a per-user random salt."""
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        dklen=32,
    )
    return f"{salt.hex()}${derived.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify plaintext password against stored scrypt hash in constant time."""
    if "$" not in stored_hash:
        return False
    salt_hex, expected_hex = stored_hash.split("$", 1)
    candidate = _hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(candidate, f"{salt_hex}${expected_hex}")


def _hash_token(raw_token: str) -> str:
    """Hash session or reset tokens with SHA-256 before persistence."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    """Manage user accounts, bearer sessions, and password reset codes in SQLite."""

    SESSION_TTL_DAYS = 7
    RESET_TTL_MINUTES = 15

    def __init__(self, db_path: str = settings.SQLITE_DB_PATH):
        self.db_path = db_path
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    registration_no TEXT,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS password_resets (
                    reset_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON auth_sessions(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_resets_user ON password_resets(user_id);")
            conn.commit()

    @staticmethod
    def _sanitize_user(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        d = dict(row)
        return {
            "user_id": d["user_id"],
            "full_name": d["full_name"],
            "email": d["email"],
            "registration_no": d.get("registration_no") or "",
            "created_at": d["created_at"],
        }

    def _issue_session(self, conn: sqlite3.Connection, user_id: str) -> str:
        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self.SESSION_TTL_DAYS)
        conn.execute(
            """
            INSERT INTO auth_sessions (token_hash, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?);
            """,
            (_hash_token(raw_token), user_id, expires.isoformat(), now.isoformat()),
        )
        return raw_token

    def register_user(
        self,
        full_name: str,
        email: str,
        password: str,
        registration_no: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Create a new user account and issue a bearer session token."""
        norm_email = _normalize_email(email)
        clean_name = full_name.strip()
        clean_reg = registration_no.strip() if registration_no else ""
        now_iso = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid.uuid4())
        pw_hash = _hash_password(password)

        with self._get_connection() as conn:
            existing = conn.execute("SELECT user_id FROM users WHERE email = ?", (norm_email,)).fetchone()
            if existing:
                raise EmailAlreadyExistsError("An account with this email already exists.")

            conn.execute(
                """
                INSERT INTO users (user_id, full_name, email, registration_no, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, clean_name, norm_email, clean_reg, pw_hash, now_iso, now_iso),
            )
            token = self._issue_session(conn, user_id)
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            conn.commit()
            return self._sanitize_user(row), token

    def login_user(self, email: str, password: str) -> Tuple[Dict[str, Any], str]:
        """Authenticate an existing user and return sanitized profile + session token."""
        norm_email = _normalize_email(email)
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (norm_email,)).fetchone()
            if not row or not _verify_password(password, row["password_hash"]):
                raise InvalidCredentialsError("Invalid email or password.")

            token = self._issue_session(conn, row["user_id"])
            conn.commit()
            return self._sanitize_user(row), token

    def get_user_by_token(self, raw_token: str) -> Optional[Dict[str, Any]]:
        """Look up an active, non-expired session by bearer token."""
        if not raw_token:
            return None
        token_hash = _hash_token(raw_token)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT u.*
                FROM auth_sessions s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?;
                """,
                (token_hash, now_iso),
            ).fetchone()
            return self._sanitize_user(row) if row else None

    def logout_token(self, raw_token: str) -> None:
        """Invalidate a bearer session token."""
        if not raw_token:
            return
        with self._get_connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_hash_token(raw_token),))
            conn.commit()

    def request_password_reset(self, email: str) -> str:
        """Generate a 6-digit OTP reset code valid for 15 minutes."""
        norm_email = _normalize_email(email)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=self.RESET_TTL_MINUTES)
        otp_code = f"{secrets.randbelow(900000) + 100000}"

        with self._get_connection() as conn:
            row = conn.execute("SELECT user_id FROM users WHERE email = ?", (norm_email,)).fetchone()
            if not row:
                raise ResetCodeError("No account found with that email address.")

            # Invalidate earlier unused reset codes for this user
            conn.execute("UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0", (row["user_id"],))
            conn.execute(
                """
                INSERT INTO password_resets (reset_id, user_id, code_hash, expires_at, used, created_at)
                VALUES (?, ?, ?, ?, 0, ?);
                """,
                (str(uuid.uuid4()), row["user_id"], _hash_token(otp_code), expires.isoformat(), now.isoformat()),
            )
            conn.commit()

        return otp_code

    def reset_password(self, email: str, reset_code: str, new_password: str) -> None:
        """Verify reset code, update user's password hash, and revoke existing sessions."""
        norm_email = _normalize_email(email)
        clean_code = reset_code.strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        code_hash = _hash_token(clean_code)

        with self._get_connection() as conn:
            user_row = conn.execute("SELECT user_id FROM users WHERE email = ?", (norm_email,)).fetchone()
            if not user_row:
                raise ResetCodeError("Invalid email or reset verification code.")

            reset_row = conn.execute(
                """
                SELECT reset_id FROM password_resets
                WHERE user_id = ? AND code_hash = ? AND used = 0 AND expires_at > ?
                ORDER BY created_at DESC LIMIT 1;
                """,
                (user_row["user_id"], code_hash, now_iso),
            ).fetchone()
            if not reset_row:
                raise ResetCodeError("Invalid or expired verification code. Please request a new code.")

            new_pw_hash = _hash_password(new_password)
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
                (new_pw_hash, now_iso, user_row["user_id"]),
            )
            conn.execute("UPDATE password_resets SET used = 1 WHERE reset_id = ?", (reset_row["reset_id"],))
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_row["user_id"],))
            conn.commit()


auth_service = AuthService()
