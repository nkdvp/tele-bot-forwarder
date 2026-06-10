from __future__ import annotations

import os
import sqlite3


_MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_initial_schema",
        """
        CREATE TABLE IF NOT EXISTS pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            group_a_chat_id INTEGER NOT NULL,
            group_b_chat_id INTEGER NOT NULL,
            bidirectional INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pair_filters (
            pair_id INTEGER PRIMARY KEY,
            types_allow_json TEXT NOT NULL,
            keywords_block_json TEXT NOT NULL,
            keywords_allow_json TEXT NOT NULL,
            FOREIGN KEY(pair_id) REFERENCES pairs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reply_links (
            src_chat_id INTEGER NOT NULL,
            src_msg_id INTEGER NOT NULL,
            dst_chat_id INTEGER NOT NULL,
            dst_msg_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (src_chat_id, src_msg_id)
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """,
    ),
]


def initialize_database(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        applied_rows = conn.execute("SELECT id FROM schema_migrations").fetchall()
        applied = {row[0] for row in applied_rows}

        for migration_id, migration_sql in _MIGRATIONS:
            if migration_id in applied:
                continue
            conn.executescript(migration_sql)
            conn.execute(
                "INSERT INTO schema_migrations (id) VALUES (?)", (migration_id,)
            )
        conn.commit()
