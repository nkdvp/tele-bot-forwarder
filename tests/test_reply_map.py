import pytest
from bot.reply_map import ReplyMap


def test_lookup_returns_none_when_not_found(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    assert store.lookup(-100111, 42) is None


def test_record_and_lookup_forward_direction(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    assert store.lookup(-100111, 100) == (-100222, 200)


def test_record_and_lookup_reverse_direction(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    assert store.lookup(-100222, 200) == (-100111, 100)


def test_persists_to_disk(tmp_path):
    path = str(tmp_path / "reply_map.json")
    store = ReplyMap(path)
    store.record(-100111, 100, -100222, 200)

    store2 = ReplyMap(path)
    assert store2.lookup(-100111, 100) == (-100222, 200)
    assert store2.lookup(-100222, 200) == (-100111, 100)


def test_multiple_entries_independent(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    store.record(-100111, 101, -100222, 201)
    assert store.lookup(-100111, 100) == (-100222, 200)
    assert store.lookup(-100111, 101) == (-100222, 201)


def test_overwrite_existing_entry(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    store.record(-100111, 100, -100222, 999)
    assert store.lookup(-100111, 100) == (-100222, 999)
