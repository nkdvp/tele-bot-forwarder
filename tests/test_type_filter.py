import pytest
from unittest.mock import MagicMock
from bot.filters.type_filter import passes_type_filter, detect_message_type
from bot.config.loader import PairConfig, FilterConfig, PairMaskingConfig


def _make_pair(allowed_types: list[str]) -> PairConfig:
    return PairConfig(
        name="p",
        group_a_chat_id=-1,
        group_b_chat_id=-2,
        bidirectional=True,
        enabled=True,
        filters=FilterConfig(
            types_allow=allowed_types,
            keywords_block=[],
            keywords_allow=[],
        ),
        masking=PairMaskingConfig(a_to_b={}, b_to_a={}),
    )


def _make_message(**kwargs) -> MagicMock:
    msg = MagicMock()
    msg.text = kwargs.get("text", None)
    msg.photo = kwargs.get("photo", None)
    msg.video = kwargs.get("video", None)
    msg.sticker = kwargs.get("sticker", None)
    msg.document = kwargs.get("document", None)
    msg.voice = kwargs.get("voice", None)
    msg.animation = kwargs.get("animation", None)
    return msg


def test_text_message_allowed():
    pair = _make_pair(["text"])
    msg = _make_message(text="hello")
    assert passes_type_filter(msg, pair) is True


def test_text_message_blocked_when_not_in_allow():
    pair = _make_pair(["photo"])
    msg = _make_message(text="hello")
    assert passes_type_filter(msg, pair) is False


def test_photo_message_allowed():
    pair = _make_pair(["photo"])
    msg = _make_message(photo=[MagicMock()])
    assert passes_type_filter(msg, pair) is True


def test_sticker_message_allowed():
    pair = _make_pair(["sticker"])
    msg = _make_message(sticker=MagicMock())
    assert passes_type_filter(msg, pair) is True


def test_unknown_message_type_blocked():
    pair = _make_pair(["text", "photo"])
    msg = _make_message()  # no known fields set
    assert passes_type_filter(msg, pair) is False


def test_detect_message_type_text():
    msg = _make_message(text="hi")
    assert detect_message_type(msg) == "text"


def test_detect_message_type_photo():
    msg = _make_message(photo=[MagicMock()])
    assert detect_message_type(msg) == "photo"


def test_detect_message_type_unknown():
    msg = _make_message()
    assert detect_message_type(msg) == "unknown"
