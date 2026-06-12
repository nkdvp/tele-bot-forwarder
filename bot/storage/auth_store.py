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
    global_role: str = "user"


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
                "SELECT id, global_role FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    """
                    INSERT INTO users (username, password_hash, is_active, global_role)
                    VALUES (?, ?, 1, 'super_admin')
                    """,
                    (username, hash_password(password)),
                )
                user_id = int(cur.lastrowid)
            else:
                user_id = int(row["id"])
                if str(row["global_role"]) == "user":
                    conn.execute(
                        "UPDATE users SET global_role = 'super_admin' WHERE id = ?",
                        (user_id,),
                    )

            default_team = conn.execute(
                "SELECT id FROM teams WHERE name = 'Default'"
            ).fetchone()
            if default_team is None:
                cur = conn.execute("INSERT INTO teams (name) VALUES ('Default')")
                team_id = int(cur.lastrowid)
            else:
                team_id = int(default_team["id"])
            conn.execute(
                """
                INSERT OR IGNORE INTO team_members (team_id, user_id, role)
                VALUES (?, ?, 'owner')
                """,
                (team_id, user_id),
            )
            conn.commit()

    def create_user(
        self,
        *,
        username: str,
        password: str,
        global_role: str = "user",
        is_active: bool = True,
    ) -> UserRecord:
        username = username.strip()
        if not username:
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")
        if global_role not in {"super_admin", "admin", "user"}:
            raise ValueError("invalid global role")
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO users (username, password_hash, is_active, global_role)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        username,
                        hash_password(password),
                        1 if is_active else 0,
                        global_role,
                    ),
                )
                conn.commit()
                user_id = int(cur.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError("username already exists") from exc
        user = self.get_user_by_id(user_id)
        assert user is not None
        return user

    def list_users(self) -> list[UserRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, username, password_hash, is_active, global_role
                FROM users
                ORDER BY username ASC
                """
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def get_user_by_id(self, user_id: int) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, is_active, global_role
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def update_user(
        self,
        user_id: int,
        *,
        global_role: str,
        is_active: bool,
        password: str | None = None,
    ) -> None:
        if global_role not in {"super_admin", "admin", "user"}:
            raise ValueError("invalid global role")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if existing is None:
                raise ValueError("user not found")
            if password:
                conn.execute(
                    """
                    UPDATE users
                    SET global_role = ?, is_active = ?, password_hash = ?
                    WHERE id = ?
                    """,
                    (global_role, 1 if is_active else 0, hash_password(password), user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET global_role = ?, is_active = ? WHERE id = ?",
                    (global_role, 1 if is_active else 0, user_id),
                )
            conn.commit()

    def count_active_super_admins(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE global_role = 'super_admin' AND is_active = 1
                """
            ).fetchone()
        return int(row[0])

    def delete_user(self, user_id: int) -> None:
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,),
            ).rowcount
            conn.commit()
        if deleted == 0:
            raise ValueError("user not found")

    def get_user_by_username(self, username: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, is_active, global_role
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

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
                SELECT
                    u.id,
                    u.username,
                    u.password_hash,
                    u.is_active,
                    u.global_role,
                    s.expires_at
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

        return self._row_to_user(row)

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()

    def cleanup_expired_sessions(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_iso,))
            conn.commit()

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=int(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            is_active=bool(row["is_active"]),
            global_role=str(row["global_role"]),
        )
