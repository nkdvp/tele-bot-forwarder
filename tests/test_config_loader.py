import pytest
import yaml
import os
from bot.config.loader import load_config, Config, PairConfig, FilterConfig, GlobalMaskingConfig


MINIMAL_CONFIG = {
    "admins": [123456789],
    "masking": {"users": {}},
    "pairs": [
        {
            "name": "test-pair",
            "group_a_chat_id": -1001111111111,
            "group_b_chat_id": -1002222222222,
            "bidirectional": True,
            "enabled": True,
            "filters": {
                "types": {"allow": ["text", "photo"]},
                "keywords": {"block": [], "allow": []},
            },
            "masking": {"a_to_b": {}, "b_to_a": {}},
        }
    ],
}


def test_load_config_returns_config_object(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    assert isinstance(config, Config)


def test_load_config_admins(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    assert config.admins == [123456789]


def test_load_config_pair_fields(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    pair = config.pairs[0]
    assert pair.name == "test-pair"
    assert pair.group_a_chat_id == -1001111111111
    assert pair.group_b_chat_id == -1002222222222
    assert pair.bidirectional is True
    assert pair.enabled is True


def test_load_config_pair_defaults_bidirectional_true(tmp_path):
    data = {**MINIMAL_CONFIG}
    data["pairs"][0] = {**data["pairs"][0]}
    del data["pairs"][0]["bidirectional"]
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    assert config.pairs[0].bidirectional is True


def test_load_config_missing_pairs_raises(tmp_path):
    data = {"admins": [1], "masking": {"users": {}}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="pairs"):
        load_config(str(config_file))


def test_load_config_missing_admins_raises(tmp_path):
    data = {**MINIMAL_CONFIG}
    del data["admins"]
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="admins"):
        load_config(str(config_file))


def test_load_config_global_masking_users(tmp_path):
    data = {**MINIMAL_CONFIG}
    data["masking"] = {"users": {111: {"alias": "Alpha"}, 222: {"alias": None}}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    assert config.masking.users[111]["alias"] == "Alpha"
    assert config.masking.users[222]["alias"] is None
