from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from bot.storage.auth_store import UserRecord


TEAM_WRITE_ROLES = {"owner", "manager"}
TEAM_ROLES = {"owner", "manager", "viewer"}
GLOBAL_ROLES = {"super_admin", "admin", "user"}


@dataclass
class TeamRecord:
    id: int
    name: str


@dataclass
class TeamMemberRecord:
    team_id: int
    user_id: int
    username: str
    role: str


class AccessStore:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def is_super_admin(self, user: UserRecord) -> bool:
        return user.global_role == "super_admin"

    def can_manage_users(self, user: UserRecord) -> bool:
        return user.global_role in {"super_admin", "admin"}

    def can_manage_teams(self, user: UserRecord) -> bool:
        return user.global_role in {"super_admin", "admin"}

    def accessible_team_ids(self, user: UserRecord) -> list[int] | None:
        if self.is_super_admin(user):
            return None
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT team_id
                FROM team_members
                WHERE user_id = ?
                ORDER BY team_id ASC
                """,
                (user.id,),
            ).fetchall()
        return [int(row["team_id"]) for row in rows]

    def writable_team_ids(self, user: UserRecord) -> list[int] | None:
        if self.is_super_admin(user):
            return None
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT team_id
                FROM team_members
                WHERE user_id = ? AND role IN ('owner', 'manager')
                ORDER BY team_id ASC
                """,
                (user.id,),
            ).fetchall()
        return [int(row["team_id"]) for row in rows]

    def can_write_team(self, user: UserRecord, team_id: int | None) -> bool:
        if team_id is None:
            return False
        writable = self.writable_team_ids(user)
        return writable is None or team_id in writable

    def list_teams(self, user: UserRecord | None = None) -> list[TeamRecord]:
        params: list[object] = []
        where_sql = ""
        if user is not None and not self.is_super_admin(user):
            team_ids = self.accessible_team_ids(user)
            if not team_ids:
                return []
            placeholders = ",".join("?" for _ in team_ids)
            where_sql = f"WHERE id IN ({placeholders})"
            params.extend(team_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, name FROM teams {where_sql} ORDER BY name ASC",
                params,
            ).fetchall()
        return [TeamRecord(id=int(row["id"]), name=str(row["name"])) for row in rows]

    def list_writable_teams(self, user: UserRecord) -> list[TeamRecord]:
        if self.is_super_admin(user):
            return self.list_teams()
        team_ids = self.writable_team_ids(user)
        if not team_ids:
            return []
        placeholders = ",".join("?" for _ in team_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, name
                FROM teams
                WHERE id IN ({placeholders})
                ORDER BY name ASC
                """,
                team_ids,
            ).fetchall()
        return [TeamRecord(id=int(row["id"]), name=str(row["name"])) for row in rows]

    def get_team(self, team_id: int) -> TeamRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name FROM teams WHERE id = ?",
                (team_id,),
            ).fetchone()
        if row is None:
            return None
        return TeamRecord(id=int(row["id"]), name=str(row["name"]))

    def create_team(self, name: str) -> TeamRecord:
        name = name.strip()
        if not name:
            raise ValueError("team name is required")
        try:
            with self._connect() as conn:
                cur = conn.execute("INSERT INTO teams (name) VALUES (?)", (name,))
                conn.commit()
                team_id = int(cur.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError("team name already exists") from exc
        return TeamRecord(id=team_id, name=name)

    def update_team(self, *, team_id: int, name: str) -> TeamRecord:
        name = name.strip()
        if not name:
            raise ValueError("team name is required")
        try:
            with self._connect() as conn:
                updated = conn.execute(
                    "UPDATE teams SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (name, team_id),
                ).rowcount
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("team name already exists") from exc
        if updated == 0:
            raise ValueError("team not found")
        team = self.get_team(team_id)
        assert team is not None
        return team

    def delete_team(self, team_id: int) -> None:
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM teams WHERE id = ?",
                (team_id,),
            ).rowcount
            conn.commit()
        if deleted == 0:
            raise ValueError("team not found")

    def list_team_members(self, team_id: int) -> list[TeamMemberRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tm.team_id, tm.user_id, u.username, tm.role
                FROM team_members tm
                JOIN users u ON u.id = tm.user_id
                WHERE tm.team_id = ?
                ORDER BY u.username ASC
                """,
                (team_id,),
            ).fetchall()
        return [
            TeamMemberRecord(
                team_id=int(row["team_id"]),
                user_id=int(row["user_id"]),
                username=str(row["username"]),
                role=str(row["role"]),
            )
            for row in rows
        ]

    def upsert_team_member(self, *, team_id: int, user_id: int, role: str) -> None:
        if role not in TEAM_ROLES:
            raise ValueError("invalid team role")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO team_members (team_id, user_id, role)
                VALUES (?, ?, ?)
                ON CONFLICT(team_id, user_id)
                DO UPDATE SET role = excluded.role
                """,
                (team_id, user_id, role),
            )
            conn.commit()

    def remove_team_member(self, *, team_id: int, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
                (team_id, user_id),
            )
            conn.commit()
