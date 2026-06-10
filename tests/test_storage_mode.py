import sqlite3

from bot.runtime.storage_mode import build_storage_dependencies, use_db_config_mode
from bot.reply_map import ReplyMap
from bot.storage.config_store import SQLiteConfigStore
from bot.storage.reply_link_store import SQLiteReplyLinkStore


def test_use_db_config_mode_parses_truthy_values():
    assert use_db_config_mode("true") is True
    assert use_db_config_mode("1") is True
    assert use_db_config_mode("yes") is True
    assert use_db_config_mode("on") is True


def test_use_db_config_mode_defaults_false():
    assert use_db_config_mode(None) is False
    assert use_db_config_mode("false") is False
    assert use_db_config_mode("0") is False


def test_build_storage_dependencies_uses_file_mode(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    json_path = str(tmp_path / "reply_map.json")

    deps = build_storage_dependencies(
        use_db=False, db_path=db_path, reply_map_path=json_path
    )

    assert deps.config_store is None
    assert isinstance(deps.reply_link_store, ReplyMap)


def test_build_storage_dependencies_uses_db_mode(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    json_path = str(tmp_path / "reply_map.json")

    deps = build_storage_dependencies(
        use_db=True, db_path=db_path, reply_map_path=json_path
    )

    assert isinstance(deps.config_store, SQLiteConfigStore)
    assert isinstance(deps.reply_link_store, SQLiteReplyLinkStore)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM schema_migrations WHERE id = '001_initial_schema'"
        ).fetchone()
    assert row is not None
