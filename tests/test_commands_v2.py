import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock
from bot.config.loader import load_config
from bot.stats.counter import StatsCounter


# ── helpers ──────────────────────────────────────────────────────────────────

MINIMAL = {
    "admins": [111],
    "masking": {"users": {}},
    "pairs": [{
        "name": "p1",
        "group_a_chat_id": -100111,
        "group_b_chat_id": -100222,
        "bidirectional": True,
        "enabled": True,
        "filters": {"types": {"allow": ["text"]}, "keywords": {"block": [], "allow": []}},
        "masking": {"a_to_b": {}, "b_to_a": {}},
    }],
}


def _cfg(tmp_path, extra=None):
    data = {**MINIMAL, **(extra or {})}
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return load_config(str(p)), str(p)


def _update(user_id: int):
    u = MagicMock()
    u.effective_user.id = user_id
    u.message.reply_text = AsyncMock()
    return u


def _ctx(*args):
    c = MagicMock()
    c.args = list(args)
    return c


# ── /set tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_recovery_window(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_set(_update(111), _ctx("recovery_window", "30"), config=config)
    assert config.recovery_window_minutes == 30


@pytest.mark.asyncio
async def test_set_recovery_window_invalid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_set(u, _ctx("recovery_window", "notanumber"), config=config)
    u.message.reply_text.assert_called_once()
    assert "Invalid" in u.message.reply_text.call_args[0][0]
    assert config.recovery_window_minutes == 15  # unchanged


@pytest.mark.asyncio
async def test_set_alert_chat(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_set(_update(111), _ctx("alert_chat", "999888777"), config=config)
    assert config.monitoring is not None
    assert config.monitoring.alert_chat_id == 999888777


@pytest.mark.asyncio
async def test_set_unknown_key_replies_usage(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_set(u, _ctx("unknown_key", "value"), config=config)
    u.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_set_unauthorized_ignored(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(999)  # not an admin
    await cmd_set(u, _ctx("recovery_window", "30"), config=config)
    u.message.reply_text.assert_not_called()
    assert config.recovery_window_minutes == 15


# ── /admin tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_add(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_admin(_update(111), _ctx("add", "222"), config=config)
    assert 222 in config.admins


@pytest.mark.asyncio
async def test_admin_add_duplicate_is_idempotent(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_admin(_update(111), _ctx("add", "111"), config=config)
    assert config.admins.count(111) == 1  # no duplicate


@pytest.mark.asyncio
async def test_admin_remove_valid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path, extra={"admins": [111, 222]})
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_admin(_update(111), _ctx("remove", "222"), config=config)
    assert 222 not in config.admins


@pytest.mark.asyncio
async def test_admin_remove_last_admin_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path)  # only admin is 111
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_admin(u, _ctx("remove", "111"), config=config)
    assert 111 in config.admins
    u.message.reply_text.assert_called_once()
    assert "last admin" in u.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_admin_remove_self_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path, extra={"admins": [111, 222]})
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_admin(u, _ctx("remove", "111"), config=config)
    assert 111 in config.admins
    u.message.reply_text.assert_called_once()
    assert "yourself" in u.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_admin_remove_nonexistent_id(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path, extra={"admins": [111, 222]})
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_admin(u, _ctx("remove", "999"), config=config)
    assert 111 in config.admins and 222 in config.admins
    u.message.reply_text.assert_called_once()
    assert "not an admin" in u.message.reply_text.call_args[0][0].lower()


# ── /pair tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pair_add_valid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_pair(_update(111), _ctx("add", "new-pair", "-100333", "-100444"), config=config)
    names = [p.name for p in config.pairs]
    assert "new-pair" in names


@pytest.mark.asyncio
async def test_pair_add_blocked_in_read_only_mode(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_pair(
        u,
        _ctx("add", "new-pair", "-100333", "-100444"),
        config=config,
        allow_mutations=False,
    )
    names = [p.name for p in config.pairs]
    assert "new-pair" not in names
    u.message.reply_text.assert_called_once()
    assert "web admin" in u.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_pair_add_bidirectional_false(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_pair(_update(111), _ctx("add", "one-way", "-100333", "-100444", "false"), config=config)
    pair = next(p for p in config.pairs if p.name == "one-way")
    assert pair.bidirectional is False


@pytest.mark.asyncio
async def test_pair_add_duplicate_name_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_pair(u, _ctx("add", "p1", "-100333", "-100444"), config=config)
    u.message.reply_text.assert_called_once()
    assert "already exists" in u.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_pair_add_invalid_chat_id_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_pair(u, _ctx("add", "new-pair", "notanid", "-100444"), config=config)
    u.message.reply_text.assert_called_once()
    assert "Invalid chat ID" in u.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_pair_remove_valid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_pair(_update(111), _ctx("remove", "p1"), config=config)
    names = [p.name for p in config.pairs]
    assert "p1" not in names


@pytest.mark.asyncio
async def test_pair_remove_unknown_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_pair(u, _ctx("remove", "ghost"), config=config)
    u.message.reply_text.assert_called_once()
    assert "not found" in u.message.reply_text.call_args[0][0]


# ── /stats tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_all_pairs(tmp_path):
    from bot.handlers.commands import cmd_stats
    config, _ = _cfg(tmp_path)
    stats = StatsCounter(str(tmp_path / "stats.json"))
    stats.increment("p1")
    stats.increment("p1")
    u = _update(111)
    await cmd_stats(u, _ctx(), config=config, stats=stats)
    u.message.reply_text.assert_called_once()
    reply = u.message.reply_text.call_args[0][0]
    assert "p1" in reply
    assert "2 today" in reply


@pytest.mark.asyncio
async def test_stats_single_pair(tmp_path):
    from bot.handlers.commands import cmd_stats
    config, _ = _cfg(tmp_path)
    stats = StatsCounter(str(tmp_path / "stats.json"))
    stats.increment("p1")
    u = _update(111)
    await cmd_stats(u, _ctx("p1"), config=config, stats=stats)
    reply = u.message.reply_text.call_args[0][0]
    assert "p1" in reply
    assert "1 today" in reply


@pytest.mark.asyncio
async def test_stats_unknown_pair(tmp_path):
    from bot.handlers.commands import cmd_stats
    config, _ = _cfg(tmp_path)
    stats = StatsCounter(str(tmp_path / "stats.json"))
    u = _update(111)
    await cmd_stats(u, _ctx("ghost"), config=config, stats=stats)
    reply = u.message.reply_text.call_args[0][0]
    assert "not found" in reply
