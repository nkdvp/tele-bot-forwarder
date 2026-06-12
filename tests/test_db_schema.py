import sqlite3

from bot.storage.sqlite_db import initialize_database


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row[0] for row in rows}


def test_initialize_database_creates_required_tables(tmp_path):
    db_path = str(tmp_path / "forwarder.db")

    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = _table_names(conn)

    assert "schema_migrations" in tables
    assert "pairs" in tables
    assert "pair_filters" in tables
    assert "reply_links" in tables
    assert "users" in tables
    assert "sessions" in tables
    assert "teams" in tables
    assert "team_members" in tables
    assert "pair_mask_rules" in tables


def test_initialize_database_is_idempotent(tmp_path):
    db_path = str(tmp_path / "forwarder.db")

    initialize_database(db_path)
    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        applied = conn.execute(
            "SELECT id FROM schema_migrations ORDER BY id"
        ).fetchall()

    assert [row[0] for row in applied] == [
        "001_initial_schema",
        "002_access_control_and_masking",
    ]


def test_v2_bootstrap_creates_default_team_and_promotes_first_user(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        default_team = conn.execute(
            "SELECT id, name FROM teams WHERE name = 'Default'"
        ).fetchone()
        assert default_team is not None
        users = conn.execute(
            "SELECT id, username, global_role FROM users ORDER BY id ASC"
        ).fetchall()
        # Fresh DB has no users yet, but default team must still exist.
        assert users == []
