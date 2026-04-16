import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bot.handlers.message import handle_message
from bot.config.loader import (
    Config, GlobalMaskingConfig, PairConfig, FilterConfig, PairMaskingConfig
)


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
    context.bot.id = 1  # different from sender (999)

    return update, context


@pytest.mark.asyncio
async def test_age_filter_skips_stale_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=20 * 60)
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        await handle_message(update, context, config=config, store=store, stats=stats)

    mock_fwd.assert_not_called()
    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_age_filter_passes_recent_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=5 * 60)
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats)

    mock_fwd.assert_called_once()
    stats.increment.assert_called_once_with("test-pair")


@pytest.mark.asyncio
async def test_age_filter_disabled_when_zero():
    config = _make_config(recovery_window_minutes=0)
    update, context = _make_update_and_context(age_seconds=60 * 60)  # 1 hour old
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats)

    mock_fwd.assert_called_once()


@pytest.mark.asyncio
async def test_stats_not_incremented_when_message_dropped_by_filter():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context()
    # Pair is disabled
    config.pairs[0].enabled = False
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock):
        await handle_message(update, context, config=config, store=store, stats=stats)

    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_stats_not_incremented_when_relay_raises():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=0)
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock, side_effect=Exception("relay failed")):
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            with pytest.raises(Exception, match="relay failed"):
                await handle_message(update, context, config=config, store=store, stats=stats)

    stats.increment.assert_not_called()
