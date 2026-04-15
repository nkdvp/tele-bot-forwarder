import pytest
import json
import os
from bot.masking.engine import resolve_display_name, MaskStore
from bot.config.loader import Config, GlobalMaskingConfig, PairConfig, FilterConfig, PairMaskingConfig


def _make_config(global_users: dict, pair_a_to_b: dict = None, pair_b_to_a: dict = None) -> Config:
    return Config(
        admins=[1],
        masking=GlobalMaskingConfig(users={int(k): v for k, v in global_users.items()}),
        pairs=[
            PairConfig(
                name="test-pair",
                group_a_chat_id=-1,
                group_b_chat_id=-2,
                bidirectional=True,
                enabled=True,
                filters=FilterConfig(types_allow=["text"], keywords_block=[], keywords_allow=[]),
                masking=PairMaskingConfig(
                    a_to_b={int(k): v for k, v in (pair_a_to_b or {}).items()},
                    b_to_a={int(k): v for k, v in (pair_b_to_a or {}).items()},
                ),
            )
        ],
        _raw={},
    )


def test_no_masking_returns_real_name(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={})
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert result == "John"


def test_global_fixed_alias(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={111: {"alias": "Customer Alpha"}})
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert result == "Customer Alpha"


def test_global_anon_id_assigned_consistently(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={111: {"alias": None}})
    pair = config.pairs[0]
    first = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    second = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert first == second
    assert first.startswith("User #")


def test_global_anon_different_users_different_numbers(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={111: {"alias": None}, 222: {"alias": None}})
    pair = config.pairs[0]
    r1 = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    r2 = resolve_display_name(222, "Jane", pair, "a_to_b", config, store)
    assert r1 != r2


def test_pair_override_takes_priority_over_global(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(
        global_users={111: {"alias": "Global Name"}},
        pair_a_to_b={111: {"alias": "VIP Override"}},
    )
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert result == "VIP Override"


def test_pair_direction_a_to_b_not_applied_for_b_to_a(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(
        global_users={},
        pair_a_to_b={111: {"alias": "A-side name"}},
    )
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "b_to_a", config, store)
    assert result == "John"


def test_mask_store_persists_to_disk(tmp_path):
    mask_path = str(tmp_path / "masks.json")
    store = MaskStore(mask_path)
    config = _make_config(global_users={111: {"alias": None}})
    pair = config.pairs[0]
    resolve_display_name(111, "John", pair, "a_to_b", config, store)

    store2 = MaskStore(mask_path)
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store2)
    assert result.startswith("User #")
