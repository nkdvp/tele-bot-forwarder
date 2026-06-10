from __future__ import annotations

import sqlite3


class SQLiteReplyLinkStore:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def lookup(self, chat_id: int, msg_id: int) -> tuple[int, int] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT dst_chat_id, dst_msg_id
                FROM reply_links
                WHERE src_chat_id = ? AND src_msg_id = ?
                """,
                (chat_id, msg_id),
            ).fetchone()
        if row is None:
            return None
        return int(row["dst_chat_id"]), int(row["dst_msg_id"])

    def record(self, src_chat: int, src_msg: int, dst_chat: int, dst_msg: int) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT dst_chat_id, dst_msg_id
                FROM reply_links
                WHERE src_chat_id = ? AND src_msg_id = ?
                """,
                (src_chat, src_msg),
            ).fetchone()
            if existing is not None:
                old_dst_chat = int(existing["dst_chat_id"])
                old_dst_msg = int(existing["dst_msg_id"])
                if old_dst_chat != dst_chat or old_dst_msg != dst_msg:
                    conn.execute(
                        """
                        DELETE FROM reply_links
                        WHERE src_chat_id = ? AND src_msg_id = ?
                        """,
                        (old_dst_chat, old_dst_msg),
                    )

            conn.execute(
                """
                INSERT OR REPLACE INTO reply_links (
                    src_chat_id, src_msg_id, dst_chat_id, dst_msg_id
                ) VALUES (?, ?, ?, ?)
                """,
                (src_chat, src_msg, dst_chat, dst_msg),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO reply_links (
                    src_chat_id, src_msg_id, dst_chat_id, dst_msg_id
                ) VALUES (?, ?, ?, ?)
                """,
                (dst_chat, dst_msg, src_chat, src_msg),
            )
            conn.commit()
