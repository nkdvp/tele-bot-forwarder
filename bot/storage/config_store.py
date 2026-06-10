from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Protocol


@dataclass
class PairFilters:
    types_allow: list[str]
    keywords_block: list[str]
    keywords_allow: list[str]


@dataclass
class PairRecord:
    id: int | None
    name: str
    group_a_chat_id: int
    group_b_chat_id: int
    bidirectional: bool
    enabled: bool
    filters: PairFilters


class ConfigStore(Protocol):
    def list_pairs(
        self,
        *,
        name_query: str | None = None,
        chat_id: int | None = None,
        enabled: bool | None = None,
        bidirectional: bool | None = None,
    ) -> list[PairRecord]:
        ...

    def get_pair_by_name(self, name: str) -> PairRecord | None:
        ...

    def create_pair(self, pair: PairRecord) -> PairRecord:
        ...

    def update_pair(self, pair: PairRecord) -> None:
        ...

    def delete_pair(self, name: str) -> None:
        ...


class SQLiteConfigStore:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def list_pairs(
        self,
        *,
        name_query: str | None = None,
        chat_id: int | None = None,
        enabled: bool | None = None,
        bidirectional: bool | None = None,
    ) -> list[PairRecord]:
        conditions: list[str] = []
        params: list[object] = []

        if name_query:
            conditions.append("p.name LIKE ?")
            params.append(f"%{name_query}%")
        if chat_id is not None:
            conditions.append("(p.group_a_chat_id = ? OR p.group_b_chat_id = ?)")
            params.extend([chat_id, chat_id])
        if enabled is not None:
            conditions.append("p.enabled = ?")
            params.append(1 if enabled else 0)
        if bidirectional is not None:
            conditions.append("p.bidirectional = ?")
            params.append(1 if bidirectional else 0)

        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                p.id,
                p.name,
                p.group_a_chat_id,
                p.group_b_chat_id,
                p.bidirectional,
                p.enabled,
                f.types_allow_json,
                f.keywords_block_json,
                f.keywords_allow_json
            FROM pairs p
            JOIN pair_filters f ON f.pair_id = p.id
            {where_sql}
            ORDER BY p.name ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_pair(row) for row in rows]

    def get_pair_by_name(self, name: str) -> PairRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p.group_a_chat_id,
                    p.group_b_chat_id,
                    p.bidirectional,
                    p.enabled,
                    f.types_allow_json,
                    f.keywords_block_json,
                    f.keywords_allow_json
                FROM pairs p
                JOIN pair_filters f ON f.pair_id = p.id
                WHERE p.name = ?
                """,
                (name,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_pair(row)

    def create_pair(self, pair: PairRecord) -> PairRecord:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO pairs (
                        name,
                        group_a_chat_id,
                        group_b_chat_id,
                        bidirectional,
                        enabled
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pair.name,
                        pair.group_a_chat_id,
                        pair.group_b_chat_id,
                        1 if pair.bidirectional else 0,
                        1 if pair.enabled else 0,
                    ),
                )
                pair_id = int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO pair_filters (
                        pair_id,
                        types_allow_json,
                        keywords_block_json,
                        keywords_allow_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        pair_id,
                        json.dumps(pair.filters.types_allow),
                        json.dumps(pair.filters.keywords_block),
                        json.dumps(pair.filters.keywords_allow),
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("Pair create failed due to integrity constraint") from exc

        return PairRecord(
            id=pair_id,
            name=pair.name,
            group_a_chat_id=pair.group_a_chat_id,
            group_b_chat_id=pair.group_b_chat_id,
            bidirectional=pair.bidirectional,
            enabled=pair.enabled,
            filters=pair.filters,
        )

    def update_pair(self, pair: PairRecord) -> None:
        if pair.id is None:
            raise ValueError("pair.id is required for updates")
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE pairs
                    SET
                        name = ?,
                        group_a_chat_id = ?,
                        group_b_chat_id = ?,
                        bidirectional = ?,
                        enabled = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        pair.name,
                        pair.group_a_chat_id,
                        pair.group_b_chat_id,
                        1 if pair.bidirectional else 0,
                        1 if pair.enabled else 0,
                        pair.id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE pair_filters
                    SET
                        types_allow_json = ?,
                        keywords_block_json = ?,
                        keywords_allow_json = ?
                    WHERE pair_id = ?
                    """,
                    (
                        json.dumps(pair.filters.types_allow),
                        json.dumps(pair.filters.keywords_block),
                        json.dumps(pair.filters.keywords_allow),
                        pair.id,
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("Pair update failed due to integrity constraint") from exc

    def delete_pair(self, name: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pairs WHERE name = ?", (name,))
            conn.commit()

    @staticmethod
    def _row_to_pair(row: sqlite3.Row) -> PairRecord:
        return PairRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            group_a_chat_id=int(row["group_a_chat_id"]),
            group_b_chat_id=int(row["group_b_chat_id"]),
            bidirectional=bool(row["bidirectional"]),
            enabled=bool(row["enabled"]),
            filters=PairFilters(
                types_allow=list(json.loads(row["types_allow_json"])),
                keywords_block=list(json.loads(row["keywords_block_json"])),
                keywords_allow=list(json.loads(row["keywords_allow_json"])),
            ),
        )
