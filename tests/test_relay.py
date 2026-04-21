import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.forwarder.relay import forward_message
from bot.reply_map import ReplyMap
from bot.config.loader import Config, GlobalMaskingConfig, PairMaskingConfig, PairConfig, FilterConfig


def _make_config(strip_mentions: bool = True) -> Config:
    return Config(
        admins=[1],
        masking=GlobalMaskingConfig(users={}),
        pairs=[],
        strip_mentions=strip_mentions,
        _raw={},
    )


def _make_message(
    text: str = "hello world",
    reply_to_id: int = None,
    chat_id: int = -100111,
    msg_id: int = 42,
):
    msg = MagicMock()
    msg.chat.id = chat_id
    msg.message_id = msg_id
    msg.text = text
    msg.caption = None
    msg.photo = None
    msg.video = None
    msg.document = None
    msg.voice = None
    msg.sticker = None
    msg.animation = None
    msg.reply_to_message = None
    if reply_to_id is not None:
        msg.reply_to_message = MagicMock()
        msg.reply_to_message.message_id = reply_to_id
    return msg


def _make_context(sent_msg_id: int = 99):
    context = MagicMock()
    sent = MagicMock()
    sent.message_id = sent_msg_id
    context.bot.send_message = AsyncMock(return_value=sent)
    context.bot.send_photo = AsyncMock(return_value=sent)
    context.bot.send_video = AsyncMock(return_value=sent)
    context.bot.send_document = AsyncMock(return_value=sent)
    context.bot.send_voice = AsyncMock(return_value=sent)
    context.bot.send_sticker = AsyncMock(return_value=sent)
    context.bot.send_animation = AsyncMock(return_value=sent)
    return context


@pytest.mark.asyncio
async def test_strip_mentions_applied_when_enabled(tmp_path):
    config = _make_config(strip_mentions=True)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    msg = _make_message(text="Hey @nicky check this")
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert "@nicky" not in sent_text
    assert "check this" in sent_text


@pytest.mark.asyncio
async def test_strip_mentions_skipped_when_disabled(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    msg = _make_message(text="Hey @nicky check this")
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert "@nicky" in sent_text


@pytest.mark.asyncio
async def test_reply_to_id_set_when_lookup_succeeds(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    reply_map.record(-100111, 50, -100222, 77)

    msg = _make_message(text="hello", reply_to_id=50)
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] == 77


@pytest.mark.asyncio
async def test_reply_to_id_is_none_when_lookup_misses(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))

    msg = _make_message(text="hello", reply_to_id=999)
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] is None


@pytest.mark.asyncio
async def test_reply_to_id_is_none_when_no_reply(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))

    msg = _make_message(text="hello")
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] is None


@pytest.mark.asyncio
async def test_sent_message_recorded_in_reply_map(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))

    msg = _make_message(text="hello", chat_id=-100111, msg_id=42)
    context = _make_context(sent_msg_id=88)

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert reply_map.lookup(-100111, 42) == (-100222, 88)
    assert reply_map.lookup(-100222, 88) == (-100111, 42)


@pytest.mark.asyncio
async def test_cross_group_reply_chain(tmp_path):
    """Message from B forwarded to A; user in A replies; reply shows in B."""
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    # B sent msg 10 → forwarded to A as msg 20
    reply_map.record(-100222, 10, -100111, 20)

    # User in A replies to msg 20 (the forwarded B message)
    msg = _make_message(text="got it", chat_id=-100111, msg_id=21, reply_to_id=20)
    context = _make_context(sent_msg_id=11)

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    # reply_to_message_id should be 10 (original message in B)
    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] == 10


@pytest.mark.asyncio
async def test_photo_caption_is_stripped(tmp_path):
    config = _make_config(strip_mentions=True)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))

    msg = _make_message()
    msg.text = None
    msg.caption = "Check @nicky photo"
    msg.photo = [MagicMock(file_id="photo_file_id")]
    context = _make_context(sent_msg_id=55)

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    call_kwargs = context.bot.send_photo.call_args.kwargs
    assert "@nicky" not in call_kwargs["caption"]
    assert "photo" in call_kwargs["caption"]


@pytest.mark.asyncio
async def test_photo_no_caption_reply_to_id_on_header(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    reply_map.record(-100111, 50, -100222, 77)

    msg = _make_message(reply_to_id=50)
    msg.text = None
    msg.caption = None
    msg.photo = [MagicMock(file_id="photo_file_id")]
    context = _make_context(sent_msg_id=55)

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    # reply_to_id goes on the header send_message, not on send_photo
    header_kwargs = context.bot.send_message.call_args.kwargs
    assert header_kwargs["reply_to_message_id"] == 77
    photo_kwargs = context.bot.send_photo.call_args.kwargs
    assert photo_kwargs["reply_to_message_id"] is None


@pytest.mark.asyncio
async def test_voice_reply_to_id_on_header_media_recorded(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    reply_map.record(-100111, 50, -100222, 77)

    msg = _make_message(reply_to_id=50, chat_id=-100111, msg_id=51)
    msg.text = None
    msg.voice = MagicMock(file_id="voice_file_id")
    context = _make_context(sent_msg_id=88)

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    # Header send_message gets reply_to_id
    header_kwargs = context.bot.send_message.call_args.kwargs
    assert header_kwargs["reply_to_message_id"] == 77
    # voice media message_id is recorded
    assert reply_map.lookup(-100111, 51) == (-100222, 88)
