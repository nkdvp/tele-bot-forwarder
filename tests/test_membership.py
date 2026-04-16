import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.handlers.membership import handle_bot_added
from bot.config.loader import Config, GlobalMaskingConfig, PairConfig, FilterConfig, PairMaskingConfig


def _make_config(admin_id: int = 111) -> Config:
    return Config(
        admins=[admin_id],
        masking=GlobalMaskingConfig(users={}),
        pairs=[],
        _raw={},
    )


def _make_update(status: str = "member", chat_type: str = "supergroup",
                 chat_id: int = -1009999999, chat_title: str = "Test Group",
                 old_status: str = "left"):
    new_member = MagicMock()
    new_member.status = status

    old_member = MagicMock()
    old_member.status = old_status

    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type
    chat.title = chat_title

    chat_member_updated = MagicMock()
    chat_member_updated.new_chat_member = new_member
    chat_member_updated.old_chat_member = old_member
    chat_member_updated.chat = chat

    update = MagicMock()
    update.my_chat_member = chat_member_updated
    return update


@pytest.mark.asyncio
async def test_bot_added_sends_dm_to_first_admin():
    config = _make_config(admin_id=111)
    update = _make_update(status="member", chat_id=-1009999999, chat_title="Support Group")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_called_once()
    assert context.bot.send_message.call_args.kwargs["chat_id"] == 111
    text = context.bot.send_message.call_args.kwargs["text"]
    assert "-1009999999" in text
    assert "Support Group" in text
    assert "/pair add" in text


@pytest.mark.asyncio
async def test_bot_added_ignored_for_non_group():
    config = _make_config()
    update = _make_update(status="member", chat_type="private")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_bot_added_ignored_when_removed():
    config = _make_config()
    update = _make_update(status="left")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_bot_added_dm_failure_does_not_crash():
    config = _make_config()
    update = _make_update(status="member")
    context = MagicMock()
    context.bot.send_message = AsyncMock(side_effect=Exception("Forbidden"))

    # Should not raise
    await handle_bot_added(update, context, config=config)


@pytest.mark.asyncio
async def test_bot_added_ignored_when_no_admins():
    config = _make_config()
    config.admins = []
    update = _make_update(status="member")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_bot_re_promotion_ignored():
    config = _make_config(admin_id=111)
    # Bot was already a member, now promoted to administrator
    update = _make_update(status="administrator", old_status="member")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_not_called()
