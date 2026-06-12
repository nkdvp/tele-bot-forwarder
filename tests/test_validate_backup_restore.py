import sqlite3

from deploy.validate_backup_restore import validate_backup


def test_validate_backup_requires_v2_tables(tmp_path):
    db_path = tmp_path / "backup.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (id TEXT PRIMARY KEY);
            CREATE TABLE pairs (id INTEGER PRIMARY KEY);
            CREATE TABLE pair_filters (pair_id INTEGER PRIMARY KEY);
            CREATE TABLE reply_links (src_chat_id INTEGER, src_msg_id INTEGER);
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            CREATE TABLE sessions (id TEXT PRIMARY KEY);
            """
        )

    ok, message = validate_backup(str(db_path))
    assert ok is False
    assert "pair_mask_rules" in message
    assert "team_members" in message
    assert "teams" in message
