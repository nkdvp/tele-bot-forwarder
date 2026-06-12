from __future__ import annotations

import argparse
import sqlite3
import sys


REQUIRED_TABLES = {
    "schema_migrations",
    "pairs",
    "pair_filters",
    "reply_links",
    "users",
    "sessions",
    "teams",
    "team_members",
    "pair_mask_rules",
}


def validate_backup(path: str) -> tuple[bool, str]:
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
    except sqlite3.Error as exc:
        return False, f"Failed to open sqlite backup: {exc}"

    table_names = {row[0] for row in rows}
    missing = sorted(REQUIRED_TABLES - table_names)
    if missing:
        return False, f"Missing required tables: {', '.join(missing)}"
    return True, "Backup looks valid"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SQLite backup file")
    parser.add_argument("--backup", required=True, help="Path to backup DB file")
    args = parser.parse_args()

    ok, message = validate_backup(args.backup)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
