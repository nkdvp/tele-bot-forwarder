import json
import sqlite3
import subprocess
from pathlib import Path

import yaml

from bot.storage.db_migration import migrate_files_to_db
from bot.storage.sqlite_db import initialize_database


def _write_config(path: Path, *, name: str = "pair-a") -> None:
    data = {
        "admins": [123456],
        "pairs": [
            {
                "name": name,
                "group_a_chat_id": -100111,
                "group_b_chat_id": -100222,
                "bidirectional": True,
                "enabled": True,
                "filters": {
                    "types": {"allow": ["text", "photo"]},
                    "keywords": {"block": ["spam"], "allow": []},
                },
            }
        ],
    }
    path.write_text(yaml.safe_dump(data))


def _write_reply_map(path: Path) -> None:
    data = {
        "-100111:10": [-100222, 20],
        "-100222:20": [-100111, 10],
    }
    path.write_text(json.dumps(data))


def test_migrate_files_to_db_imports_pairs_and_reply_links(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    config_path = tmp_path / "config.yaml"
    reply_map_path = tmp_path / "reply_map.json"
    _write_config(config_path)
    _write_reply_map(reply_map_path)
    initialize_database(db_path)

    report = migrate_files_to_db(
        config_path=str(config_path),
        reply_map_path=str(reply_map_path),
        db_path=db_path,
        dry_run=False,
    )

    assert report.success is True
    assert report.pairs_imported == 1
    assert report.reply_links_imported == 2
    assert report.errors == []

    with sqlite3.connect(db_path) as conn:
        pairs = conn.execute("SELECT name, team_id FROM pairs").fetchall()
        default_team = conn.execute(
            "SELECT id FROM teams WHERE name = 'Default'"
        ).fetchone()
        links = conn.execute("SELECT src_chat_id, src_msg_id FROM reply_links").fetchall()
    assert default_team is not None
    assert pairs == [("pair-a", default_team[0])]
    assert len(links) == 2


def test_migrate_files_to_db_dry_run_does_not_write(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    config_path = tmp_path / "config.yaml"
    reply_map_path = tmp_path / "reply_map.json"
    _write_config(config_path)
    _write_reply_map(reply_map_path)
    initialize_database(db_path)

    report = migrate_files_to_db(
        config_path=str(config_path),
        reply_map_path=str(reply_map_path),
        db_path=db_path,
        dry_run=True,
    )

    assert report.success is True
    assert report.pairs_imported == 1
    assert report.reply_links_imported == 2

    with sqlite3.connect(db_path) as conn:
        pair_count = conn.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
        link_count = conn.execute("SELECT COUNT(*) FROM reply_links").fetchone()[0]
    assert pair_count == 0
    assert link_count == 0


def test_migrate_files_to_db_reports_validation_errors_without_partial_writes(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    config_path = tmp_path / "config.yaml"
    reply_map_path = tmp_path / "reply_map.json"
    _write_config(config_path, name="")
    _write_reply_map(reply_map_path)
    initialize_database(db_path)

    report = migrate_files_to_db(
        config_path=str(config_path),
        reply_map_path=str(reply_map_path),
        db_path=db_path,
        dry_run=False,
    )

    assert report.success is False
    assert report.pairs_imported == 0
    assert report.reply_links_imported == 0
    assert report.errors
    assert report.errors[0]["code"] == "INVALID_PAIR"

    with sqlite3.connect(db_path) as conn:
        pair_count = conn.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
        link_count = conn.execute("SELECT COUNT(*) FROM reply_links").fetchone()[0]
    assert pair_count == 0
    assert link_count == 0


def test_migration_cli_outputs_structured_report(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    config_path = tmp_path / "config.yaml"
    reply_map_path = tmp_path / "reply_map.json"
    _write_config(config_path)
    _write_reply_map(reply_map_path)

    result = subprocess.run(
        [
            "python3",
            "-m",
            "bot.storage.db_migration",
            "--config",
            str(config_path),
            "--reply-map",
            str(reply_map_path),
            "--db",
            db_path,
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["dry_run"] is True
    assert payload["pairs_imported"] == 1
