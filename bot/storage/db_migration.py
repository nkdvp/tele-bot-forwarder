from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
import argparse
import json
import sqlite3
from typing import Any

import yaml

from bot.storage.sqlite_db import initialize_database


@dataclass
class MigrationReport:
    success: bool
    dry_run: bool
    pairs_imported: int
    reply_links_imported: int
    errors: list[dict[str, str]]


def _parse_pair(raw: dict[str, Any], idx: int) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    name = str(raw.get("name", "")).strip()
    if not name:
        return None, {
            "code": "INVALID_PAIR",
            "message": f"pairs[{idx}].name must be non-empty",
        }

    try:
        group_a_chat_id = int(raw["group_a_chat_id"])
        group_b_chat_id = int(raw["group_b_chat_id"])
    except (KeyError, TypeError, ValueError):
        return None, {
            "code": "INVALID_PAIR",
            "message": f"pairs[{idx}] has invalid group chat IDs",
        }

    filters = raw.get("filters") or {}
    types_allow = ((filters.get("types") or {}).get("allow")) or ["text"]
    keywords = filters.get("keywords") or {}
    keywords_block = keywords.get("block") or []
    keywords_allow = keywords.get("allow") or []

    return (
        {
            "name": name,
            "group_a_chat_id": group_a_chat_id,
            "group_b_chat_id": group_b_chat_id,
            "bidirectional": bool(raw.get("bidirectional", True)),
            "enabled": bool(raw.get("enabled", True)),
            "types_allow_json": json.dumps(list(types_allow)),
            "keywords_block_json": json.dumps(list(keywords_block)),
            "keywords_allow_json": json.dumps(list(keywords_allow)),
        },
        None,
    )


def _parse_reply_link(key: str, value: Any) -> tuple[dict[str, int] | None, dict[str, str] | None]:
    try:
        src_chat_raw, src_msg_raw = key.split(":", 1)
        src_chat_id = int(src_chat_raw)
        src_msg_id = int(src_msg_raw)
        dst_chat_id = int(value[0])
        dst_msg_id = int(value[1])
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return None, {
            "code": "INVALID_REPLY_LINK",
            "message": f"Invalid reply map entry for key '{key}'",
        }
    return (
        {
            "src_chat_id": src_chat_id,
            "src_msg_id": src_msg_id,
            "dst_chat_id": dst_chat_id,
            "dst_msg_id": dst_msg_id,
        },
        None,
    )


def migrate_files_to_db(
    *,
    config_path: str,
    reply_map_path: str,
    db_path: str,
    dry_run: bool = False,
) -> MigrationReport:
    errors: list[dict[str, str]] = []

    with open(config_path, "r") as f:
        config_raw = yaml.safe_load(f) or {}
    with open(reply_map_path, "r") as f:
        reply_map_raw = json.load(f) or {}

    pairs_raw = config_raw.get("pairs") or []
    parsed_pairs: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for idx, raw_pair in enumerate(pairs_raw):
        pair, pair_error = _parse_pair(raw_pair, idx)
        if pair_error is not None:
            errors.append(pair_error)
            continue
        assert pair is not None
        if pair["name"] in seen_names:
            errors.append(
                {
                    "code": "INVALID_PAIR",
                    "message": f"Duplicate pair name '{pair['name']}' in config",
                }
            )
            continue
        seen_names.add(pair["name"])
        parsed_pairs.append(pair)

    parsed_links: list[dict[str, int]] = []
    for key, value in reply_map_raw.items():
        link, link_error = _parse_reply_link(key, value)
        if link_error is not None:
            errors.append(link_error)
            continue
        assert link is not None
        parsed_links.append(link)

    if errors:
        return MigrationReport(
            success=False,
            dry_run=dry_run,
            pairs_imported=0,
            reply_links_imported=0,
            errors=errors,
        )

    if dry_run:
        return MigrationReport(
            success=True,
            dry_run=True,
            pairs_imported=len(parsed_pairs),
            reply_links_imported=len(parsed_links),
            errors=[],
        )

    initialize_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        default_team_id = conn.execute(
            "SELECT id FROM teams WHERE name = 'Default'"
        ).fetchone()[0]
        conn.execute("DELETE FROM pair_filters")
        conn.execute("DELETE FROM pairs")
        conn.execute("DELETE FROM reply_links")

        for pair in parsed_pairs:
            cur = conn.execute(
                """
                INSERT INTO pairs (
                    name,
                    group_a_chat_id,
                    group_b_chat_id,
                    bidirectional,
                    enabled,
                    team_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pair["name"],
                    pair["group_a_chat_id"],
                    pair["group_b_chat_id"],
                    1 if pair["bidirectional"] else 0,
                    1 if pair["enabled"] else 0,
                    default_team_id,
                ),
            )
            pair_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO pair_filters (
                    pair_id, types_allow_json, keywords_block_json, keywords_allow_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    pair_id,
                    pair["types_allow_json"],
                    pair["keywords_block_json"],
                    pair["keywords_allow_json"],
                ),
            )

        for link in parsed_links:
            conn.execute(
                """
                INSERT INTO reply_links (
                    src_chat_id, src_msg_id, dst_chat_id, dst_msg_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    link["src_chat_id"],
                    link["src_msg_id"],
                    link["dst_chat_id"],
                    link["dst_msg_id"],
                ),
            )
        conn.commit()

    return MigrationReport(
        success=True,
        dry_run=False,
        pairs_imported=len(parsed_pairs),
        reply_links_imported=len(parsed_links),
        errors=[],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate file-based state into SQLite DB")
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument("--reply-map", required=True, help="Path to reply_map.json")
    parser.add_argument("--db", required=True, help="Path to SQLite DB file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report without writing to database",
    )
    args = parser.parse_args()

    report = migrate_files_to_db(
        config_path=args.config,
        reply_map_path=args.reply_map,
        db_path=args.db,
        dry_run=args.dry_run,
    )
    print(json.dumps(asdict(report)))
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
