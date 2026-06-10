from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
import sqlite3


PBKDF2_ITERATIONS = 120_000


@dataclass
class UserRecord:
    id: int
    username: str
    password_hash: str
    is_active: bool


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = password_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(rounds),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


class AuthStore:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def ensure_admin_user(self, username: str, password: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, is_active)
                    VALUES (?, ?, 1)
                    """,
                    (username, hash_password(password)),
                )
                conn.commit()

    def get_user_by_username(self, username: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, is_active
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
        if row is None:
            return None
        return UserRecord(
            id=int(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            is_active=bool(row["is_active"]),
        )

    def create_session(self, user_id: int, ttl_hours: int = 24) -> str:
        session_id = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, user_id, expires_at)
                VALUES (?, ?, ?)
                """,
                (session_id, user_id, expires_at),
            )
            conn.commit()
        return session_id

    def get_user_by_session(self, session_id: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.password_hash, u.is_active, s.expires_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None

        expires_at = str(row["expires_at"])
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            return None
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expiry:
            self.delete_session(session_id)
            return None

        return UserRecord(
            id=int(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            is_active=bool(row["is_active"]),
        )

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()

    def cleanup_expired_sessions(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_iso,))
            conn.commit()
