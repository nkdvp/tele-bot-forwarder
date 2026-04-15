from __future__ import annotations
from bot.config.loader import PairConfig

_TYPE_CHECKS = [
    ("text",      lambda m: bool(m.text)),
    ("photo",     lambda m: bool(m.photo)),
    ("video",     lambda m: bool(m.video)),
    ("sticker",   lambda m: bool(m.sticker)),
    ("document",  lambda m: bool(m.document)),
    ("voice",     lambda m: bool(m.voice)),
    ("animation", lambda m: bool(m.animation)),
]


def detect_message_type(message) -> str:
    for type_name, check in _TYPE_CHECKS:
        if check(message):
            return type_name
    return "unknown"


def passes_type_filter(message, pair: PairConfig) -> bool:
    msg_type = detect_message_type(message)
    return msg_type in pair.filters.types_allow
