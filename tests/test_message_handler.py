import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bot.handlers.message import handle_message
from bot.config.loader import (
    Config, GlobalMaskingConfig, PairConfig, FilterConfig, PairMaskingConfig
)
from bot.storage.config_store import PairFilters, PairRecord
from bot.storage.config_store import PairMaskRule, SQLiteConfigStore
from bot.storage.sqlite_db import initialize_database


def _make_config(recovery_window_minutes: int = 15) -> Config:
    return Config(
        admins=[1],
        masking=GlobalMaskingConfig(users={}),
        pairs=[
            PairConfig(
                name="test-pair",
                group_a_chat_id=-100111,
                group_b_chat_id=-100222,
                bidirectional=True,
                enabled=True,
                filters=FilterConfig(
                    types_allow=["text"],
                    keywords_block=[],
                    keywords_allow=[],
                ),
                masking=PairMaskingConfig(a_to_b={}, b_to_a={}),
            )
        ],
        recovery_window_minutes=recovery_window_minutes,
        _raw={},
    )


def _make_update_and_context(age_seconds: int = 0, chat_id: int = -100111):
    message = MagicMock()
    message.from_user.id = 999
    message.from_user.first_name = "Tester"
    message.date = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    message.text = "hello"
    message.caption = None
    message.photo = None
    message.video = None
    message.document = None
    message.voice = None
    message.sticker = None
    message.animation = None

    update = MagicMock()
    update.effective_message = message
    update.effective_chat.id = chat_id

    context = MagicMock()
    context.bot.id = 1

    return update, context


@pytest.mark.asyncio
async def test_age_filter_skips_stale_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=20 * 60)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_not_called()
    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_age_filter_passes_recent_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=5 * 60)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_called_once()
    stats.increment.assert_called_once_with("test-pair")


@pytest.mark.asyncio
async def test_age_filter_disabled_when_zero():
    config = _make_config(recovery_window_minutes=0)
    update, context = _make_update_and_context(age_seconds=60 * 60)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_called_once()


@pytest.mark.asyncio
async def test_stats_not_incremented_when_message_dropped_by_filter():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context()
    config.pairs[0].enabled = False
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock):
        await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_stats_not_incremented_when_relay_raises():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=0)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock, side_effect=Exception("relay failed")):
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            with pytest.raises(Exception, match="relay failed"):
                await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_reply_map_and_config_passed_to_forward_message():
    config = _make_config(recovery_window_minutes=0)
    update, context = _make_update_and_context(age_seconds=0)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_called_once()
    call_args = mock_fwd.call_args.args
    assert call_args[4] is reply_map
    assert call_args[5] is config


@pytest.mark.asyncio
async def test_uses_db_config_store_for_pair_lookup_when_provided():
    config = _make_config(recovery_window_minutes=0)
    config.pairs = []
    update, context = _make_update_and_context(age_seconds=0)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()
    config_store = MagicMock()
    config_store.list_pairs.return_value = [
        PairRecord(
            id=1,
            name="db-pair",
            group_a_chat_id=-100111,
            group_b_chat_id=-100222,
            bidirectional=True,
            enabled=True,
            filters=PairFilters(
                types_allow=["text"],
                keywords_block=[],
                keywords_allow=[],
            ),
        )
    ]

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(
                update,
                context,
                config=config,
                store=store,
                stats=stats,
                reply_map=reply_map,
                config_store=config_store,
            )

    mock_fwd.assert_called_once()
    stats.increment.assert_called_once_with("db-pair")


@pytest.mark.asyncio
async def test_db_config_store_respects_disabled_pair():
    config = _make_config(recovery_window_minutes=0)
    config.pairs = []
    update, context = _make_update_and_context(age_seconds=0)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()
    config_store = MagicMock()
    config_store.list_pairs.return_value = [
        PairRecord(
            id=1,
            name="db-disabled",
            group_a_chat_id=-100111,
            group_b_chat_id=-100222,
            bidirectional=True,
            enabled=False,
            filters=PairFilters(
                types_allow=["text"],
                keywords_block=[],
                keywords_allow=[],
            ),
        )
    ]

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(
                update,
                context,
                config=config,
                store=store,
                stats=stats,
                reply_map=reply_map,
                config_store=config_store,
            )

    mock_fwd.assert_not_called()
    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_db_mask_rule_alias_applies_to_forwarded_display_name(tmp_path):
    config = _make_config(recovery_window_minutes=0)
    config.pairs = []
    update, context = _make_update_and_context(age_seconds=0)
    stats = MagicMock()
    reply_map = MagicMock()
    store = MagicMock()

    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    config_store = SQLiteConfigStore(db_path)
    pair = config_store.create_pair(
        PairRecord(
            id=None,
            name="db-pair",
            group_a_chat_id=-100111,
            group_b_chat_id=-100222,
            bidirectional=True,
            enabled=True,
            filters=PairFilters(types_allow=["text"], keywords_block=[], keywords_allow=[]),
        )
    )
    assert pair.id is not None
    config_store.upsert_pair_mask_rule(
        PairMaskRule(
            id=None,
            pair_id=pair.id,
            telegram_user_id=999,
            direction="a_to_b",
            mode="alias",
            alias="Customer Alias",
        )
    )

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        await handle_message(
            update,
            context,
            config=config,
            store=store,
            stats=stats,
            reply_map=reply_map,
            config_store=config_store,
        )

    mock_fwd.assert_called_once()
    assert mock_fwd.call_args.args[1] == "Customer Alias"


@pytest.mark.asyncio
async def test_db_mask_rule_anonymous_applies_and_fallback_uses_yaml_masking(tmp_path):
    config = _make_config(recovery_window_minutes=0)
    config.pairs = []
    config.masking.users[999] = {"alias": "Global Alias"}
    update, context = _make_update_and_context(age_seconds=0)
    stats = MagicMock()
    reply_map = MagicMock()
    store = MagicMock()
    store.get_anon_number.return_value = 7

    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    config_store = SQLiteConfigStore(db_path)
    pair = config_store.create_pair(
        PairRecord(
            id=None,
            name="db-pair",
            group_a_chat_id=-100111,
            group_b_chat_id=-100222,
            bidirectional=True,
            enabled=True,
            filters=PairFilters(types_allow=["text"], keywords_block=[], keywords_allow=[]),
        )
    )
    assert pair.id is not None

    config_store.upsert_pair_mask_rule(
        PairMaskRule(
            id=None,
            pair_id=pair.id,
            telegram_user_id=999,
            direction="a_to_b",
            mode="anonymous",
            alias=None,
        )
    )

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        await handle_message(
            update,
            context,
            config=config,
            store=store,
            stats=stats,
            reply_map=reply_map,
            config_store=config_store,
        )
    assert mock_fwd.call_args.args[1] == "User #7"

    # Same user in reverse direction has no DB rule -> fallback to YAML/global masking.
    update_reverse, context_reverse = _make_update_and_context(age_seconds=0, chat_id=-100222)
    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as reverse_fwd:
        await handle_message(
            update_reverse,
            context_reverse,
            config=config,
            store=store,
            stats=stats,
            reply_map=reply_map,
            config_store=config_store,
        )
    assert reverse_fwd.call_args.args[1] == "Global Alias"
