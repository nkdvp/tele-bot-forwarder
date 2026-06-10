from bot.storage.reply_link_store import SQLiteReplyLinkStore
from bot.storage.sqlite_db import initialize_database


def test_lookup_returns_none_when_not_found(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteReplyLinkStore(db_path)

    assert store.lookup(-100111, 10) is None


def test_record_and_lookup_bidirectional(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteReplyLinkStore(db_path)

    store.record(-100111, 10, -100222, 20)

    assert store.lookup(-100111, 10) == (-100222, 20)
    assert store.lookup(-100222, 20) == (-100111, 10)


def test_overwrite_removes_stale_reverse_mapping(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteReplyLinkStore(db_path)

    store.record(-100111, 10, -100222, 20)
    store.record(-100111, 10, -100222, 21)

    assert store.lookup(-100111, 10) == (-100222, 21)
    assert store.lookup(-100222, 21) == (-100111, 10)
    assert store.lookup(-100222, 20) is None
