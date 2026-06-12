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
    team_id: int | None = None
    created_by_user_id: int | None = None


@dataclass
class PairMaskRule:
    id: int | None
    pair_id: int
    telegram_user_id: int
    direction: str
    mode: str
    alias: str | None


@dataclass
class PairPage:
    pairs: list[PairRecord]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.total == 0:
            return 1
        return ((self.total - 1) // self.page_size) + 1


class ConfigStore(Protocol):
    def list_pairs(
        self,
        *,
        name_query: str | None = None,
        chat_id: int | None = None,
        enabled: bool | None = None,
        bidirectional: bool | None = None,
        team_ids: list[int] | None = None,
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
        team_ids: list[int] | None = None,
    ) -> list[PairRecord]:
        rows = self._fetch_pairs(
            name_query=name_query,
            chat_id=chat_id,
            enabled=enabled,
            bidirectional=bidirectional,
            team_ids=team_ids,
            limit=None,
            offset=None,
        )
        return [self._row_to_pair(row) for row in rows]

    def page_pairs(
        self,
        *,
        page: int,
        page_size: int,
        name_query: str | None = None,
        chat_id: int | None = None,
        enabled: bool | None = None,
        bidirectional: bool | None = None,
        team_ids: list[int] | None = None,
    ) -> PairPage:
        page = max(page, 1)
        page_size = max(page_size, 1)
        total = self.count_pairs(
            name_query=name_query,
            chat_id=chat_id,
            enabled=enabled,
            bidirectional=bidirectional,
            team_ids=team_ids,
        )
        rows = self._fetch_pairs(
            name_query=name_query,
            chat_id=chat_id,
            enabled=enabled,
            bidirectional=bidirectional,
            team_ids=team_ids,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return PairPage(
            pairs=[self._row_to_pair(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def count_pairs(
        self,
        *,
        name_query: str | None = None,
        chat_id: int | None = None,
        enabled: bool | None = None,
        bidirectional: bool | None = None,
        team_ids: list[int] | None = None,
    ) -> int:
        where_sql, params = self._pair_where_sql(
            name_query=name_query,
            chat_id=chat_id,
            enabled=enabled,
            bidirectional=bidirectional,
            team_ids=team_ids,
        )
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM pairs p {where_sql}", params).fetchone()
        return int(row[0])

    def _fetch_pairs(
        self,
        *,
        name_query: str | None,
        chat_id: int | None,
        enabled: bool | None,
        bidirectional: bool | None,
        team_ids: list[int] | None,
        limit: int | None,
        offset: int | None,
    ) -> list[sqlite3.Row]:
        where_sql, params = self._pair_where_sql(
            name_query=name_query,
            chat_id=chat_id,
            enabled=enabled,
            bidirectional=bidirectional,
            team_ids=team_ids,
        )
        paging_sql = ""
        if limit is not None:
            paging_sql = "LIMIT ? OFFSET ?"
            params.extend([limit, offset or 0])

        sql = f"""
            SELECT
                p.id,
                p.name,
                p.group_a_chat_id,
                p.group_b_chat_id,
                p.bidirectional,
                p.enabled,
                p.team_id,
                p.created_by_user_id,
                f.types_allow_json,
                f.keywords_block_json,
                f.keywords_allow_json
            FROM pairs p
            JOIN pair_filters f ON f.pair_id = p.id
            {where_sql}
            ORDER BY p.name ASC
            {paging_sql}
        """
        with self._connect() as conn:
            return conn.execute(sql, params).fetchall()

    @staticmethod
    def _pair_where_sql(
        *,
        name_query: str | None = None,
        chat_id: int | None = None,
        enabled: bool | None = None,
        bidirectional: bool | None = None,
        team_ids: list[int] | None = None,
    ) -> tuple[str, list[object]]:
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
        if team_ids is not None:
            if not team_ids:
                conditions.append("1 = 0")
            else:
                placeholders = ",".join("?" for _ in team_ids)
                conditions.append(f"p.team_id IN ({placeholders})")
                params.extend(team_ids)

        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)
        return where_sql, params

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
                    p.team_id,
                    p.created_by_user_id,
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
                        enabled,
                        team_id,
                        created_by_user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pair.name,
                        pair.group_a_chat_id,
                        pair.group_b_chat_id,
                        1 if pair.bidirectional else 0,
                        1 if pair.enabled else 0,
                        pair.team_id,
                        pair.created_by_user_id,
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
            team_id=pair.team_id,
            created_by_user_id=pair.created_by_user_id,
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
                        team_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        pair.name,
                        pair.group_a_chat_id,
                        pair.group_b_chat_id,
                        1 if pair.bidirectional else 0,
                        1 if pair.enabled else 0,
                        pair.team_id,
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

    def list_pair_mask_rules(self, pair_id: int) -> list[PairMaskRule]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, pair_id, telegram_user_id, direction, mode, alias
                FROM pair_mask_rules
                WHERE pair_id = ?
                ORDER BY telegram_user_id ASC, direction ASC
                """,
                (pair_id,),
            ).fetchall()
        return [self._row_to_mask_rule(row) for row in rows]

    def get_pair_mask_rule(
        self,
        *,
        pair_id: int,
        telegram_user_id: int,
        direction: str,
    ) -> PairMaskRule | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, pair_id, telegram_user_id, direction, mode, alias
                FROM pair_mask_rules
                WHERE pair_id = ? AND telegram_user_id = ? AND direction = ?
                """,
                (pair_id, telegram_user_id, direction),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_mask_rule(row)

    def get_pair_mask_rule_by_id(self, rule_id: int) -> PairMaskRule | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, pair_id, telegram_user_id, direction, mode, alias
                FROM pair_mask_rules
                WHERE id = ?
                """,
                (rule_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_mask_rule(row)

    def upsert_pair_mask_rule(self, rule: PairMaskRule) -> PairMaskRule:
        if rule.direction not in {"a_to_b", "b_to_a"}:
            raise ValueError("invalid direction")
        if rule.mode not in {"alias", "anonymous"}:
            raise ValueError("invalid mask mode")
        alias = rule.alias.strip() if rule.alias else None
        if rule.mode == "alias" and not alias:
            raise ValueError("alias is required")
        if rule.mode == "anonymous":
            alias = None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pair_mask_rules (
                    pair_id, telegram_user_id, direction, mode, alias
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(pair_id, telegram_user_id, direction)
                DO UPDATE SET
                    mode = excluded.mode,
                    alias = excluded.alias,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (rule.pair_id, rule.telegram_user_id, rule.direction, rule.mode, alias),
            )
            conn.commit()
        existing = self.get_pair_mask_rule(
            pair_id=rule.pair_id,
            telegram_user_id=rule.telegram_user_id,
            direction=rule.direction,
        )
        assert existing is not None
        return existing

    def delete_pair_mask_rule(self, rule_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pair_mask_rules WHERE id = ?", (rule_id,))
            conn.commit()

    def delete_pair_mask_rule_for_pair(self, *, pair_id: int, rule_id: int) -> bool:
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM pair_mask_rules WHERE id = ? AND pair_id = ?",
                (rule_id, pair_id),
            ).rowcount
            conn.commit()
        return deleted > 0

    def suggest_aliases(
        self,
        *,
        telegram_user_id: int,
        team_ids: list[int] | None = None,
        limit: int = 5,
    ) -> list[str]:
        conditions = [
            "r.telegram_user_id = ?",
            "r.mode = 'alias'",
            "r.alias IS NOT NULL",
        ]
        params: list[object] = [telegram_user_id]
        if team_ids is not None:
            if not team_ids:
                return []
            placeholders = ",".join("?" for _ in team_ids)
            conditions.append(f"p.team_id IN ({placeholders})")
            params.extend(team_ids)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT r.alias
                FROM pair_mask_rules r
                JOIN pairs p ON p.id = r.pair_id
                WHERE {" AND ".join(conditions)}
                ORDER BY r.updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [str(row["alias"]) for row in rows]

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
            team_id=int(row["team_id"]) if row["team_id"] is not None else None,
            created_by_user_id=(
                int(row["created_by_user_id"])
                if row["created_by_user_id"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_mask_rule(row: sqlite3.Row) -> PairMaskRule:
        return PairMaskRule(
            id=int(row["id"]),
            pair_id=int(row["pair_id"]),
            telegram_user_id=int(row["telegram_user_id"]),
            direction=str(row["direction"]),
            mode=str(row["mode"]),
            alias=str(row["alias"]) if row["alias"] is not None else None,
        )
