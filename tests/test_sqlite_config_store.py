from bot.storage.config_store import PairFilters, PairRecord, SQLiteConfigStore
from bot.storage.sqlite_db import initialize_database


def _sample_pair(name: str = "support") -> PairRecord:
    return PairRecord(
        id=None,
        name=name,
        group_a_chat_id=-100111,
        group_b_chat_id=-100222,
        bidirectional=True,
        enabled=True,
        filters=PairFilters(
            types_allow=["text", "photo"],
            keywords_block=["spam"],
            keywords_allow=[],
        ),
    )


def test_create_and_get_pair(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteConfigStore(db_path)

    created = store.create_pair(_sample_pair("pair-a"))
    fetched = store.get_pair_by_name("pair-a")

    assert created.id is not None
    assert fetched is not None
    assert fetched.name == "pair-a"
    assert fetched.group_a_chat_id == -100111
    assert fetched.filters.types_allow == ["text", "photo"]


def test_list_pairs_supports_filters(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteConfigStore(db_path)

    store.create_pair(_sample_pair("customer-internal"))
    store.create_pair(
        PairRecord(
            id=None,
            name="ops-one-way",
            group_a_chat_id=-100333,
            group_b_chat_id=-100444,
            bidirectional=False,
            enabled=False,
            filters=PairFilters(
                types_allow=["text"],
                keywords_block=[],
                keywords_allow=["urgent"],
            ),
        )
    )

    by_name = store.list_pairs(name_query="customer")
    by_chat = store.list_pairs(chat_id=-100444)
    by_enabled = store.list_pairs(enabled=False)
    by_direction = store.list_pairs(bidirectional=False)

    assert [p.name for p in by_name] == ["customer-internal"]
    assert [p.name for p in by_chat] == ["ops-one-way"]
    assert [p.name for p in by_enabled] == ["ops-one-way"]
    assert [p.name for p in by_direction] == ["ops-one-way"]


def test_update_and_delete_pair(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteConfigStore(db_path)

    created = store.create_pair(_sample_pair("to-edit"))
    assert created.id is not None

    updated = PairRecord(
        id=created.id,
        name="to-edit",
        group_a_chat_id=-100111,
        group_b_chat_id=-100999,
        bidirectional=False,
        enabled=False,
        filters=PairFilters(
            types_allow=["text"],
            keywords_block=["blocked"],
            keywords_allow=["allow-me"],
        ),
    )
    store.update_pair(updated)

    fetched = store.get_pair_by_name("to-edit")
    assert fetched is not None
    assert fetched.group_b_chat_id == -100999
    assert fetched.bidirectional is False
    assert fetched.enabled is False
    assert fetched.filters.keywords_block == ["blocked"]

    store.delete_pair("to-edit")
    assert store.get_pair_by_name("to-edit") is None
