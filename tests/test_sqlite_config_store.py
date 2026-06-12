import pytest

from bot.storage.config_store import (
    PairFilters,
    PairMaskRule,
    PairRecord,
    SQLiteConfigStore,
)
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


def test_pair_mask_rules_crud_direction_and_alias_suggestions(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteConfigStore(db_path)

    created = store.create_pair(_sample_pair("pair-mask"))
    assert created.id is not None

    first = store.upsert_pair_mask_rule(
        PairMaskRule(
            id=None,
            pair_id=created.id,
            telegram_user_id=12345,
            direction="a_to_b",
            mode="alias",
            alias="Alias One",
        )
    )
    assert first.id is not None
    fetched = store.get_pair_mask_rule(
        pair_id=created.id,
        telegram_user_id=12345,
        direction="a_to_b",
    )
    assert fetched is not None
    assert fetched.alias == "Alias One"

    missing_other_direction = store.get_pair_mask_rule(
        pair_id=created.id,
        telegram_user_id=12345,
        direction="b_to_a",
    )
    assert missing_other_direction is None

    updated = store.upsert_pair_mask_rule(
        PairMaskRule(
            id=first.id,
            pair_id=created.id,
            telegram_user_id=12345,
            direction="a_to_b",
            mode="alias",
            alias="Alias Updated",
        )
    )
    assert updated.id == first.id
    assert updated.alias == "Alias Updated"

    anon = store.upsert_pair_mask_rule(
        PairMaskRule(
            id=None,
            pair_id=created.id,
            telegram_user_id=12345,
            direction="b_to_a",
            mode="anonymous",
            alias="ignored",
        )
    )
    assert anon.alias is None

    aliases = store.suggest_aliases(telegram_user_id=12345)
    assert aliases == ["Alias Updated"]


def test_pair_mask_rules_validation_and_delete_guard(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteConfigStore(db_path)
    pair = store.create_pair(_sample_pair("pair-mask-2"))
    assert pair.id is not None

    with pytest.raises(ValueError, match="invalid direction"):
        store.upsert_pair_mask_rule(
            PairMaskRule(
                id=None,
                pair_id=pair.id,
                telegram_user_id=222,
                direction="invalid",
                mode="alias",
                alias="Alias",
            )
        )

    with pytest.raises(ValueError, match="alias is required"):
        store.upsert_pair_mask_rule(
            PairMaskRule(
                id=None,
                pair_id=pair.id,
                telegram_user_id=222,
                direction="a_to_b",
                mode="alias",
                alias="",
            )
        )

    saved = store.upsert_pair_mask_rule(
        PairMaskRule(
            id=None,
            pair_id=pair.id,
            telegram_user_id=333,
            direction="a_to_b",
            mode="alias",
            alias="Delete Me",
        )
    )
    assert saved.id is not None
    assert store.delete_pair_mask_rule_for_pair(pair_id=pair.id, rule_id=saved.id)
    assert not store.delete_pair_mask_rule_for_pair(pair_id=pair.id, rule_id=saved.id)


def test_pair_mask_rules_deleted_with_pair(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = SQLiteConfigStore(db_path)
    pair = store.create_pair(_sample_pair("pair-mask-3"))
    assert pair.id is not None

    rule = store.upsert_pair_mask_rule(
        PairMaskRule(
            id=None,
            pair_id=pair.id,
            telegram_user_id=777,
            direction="a_to_b",
            mode="alias",
            alias="Cascade",
        )
    )
    assert rule.id is not None

    store.delete_pair(pair.name)
    assert store.get_pair_mask_rule_by_id(rule.id) is None
