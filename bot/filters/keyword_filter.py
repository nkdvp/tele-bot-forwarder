from __future__ import annotations
from bot.config.loader import PairConfig


def passes_keyword_filter(text: str | None, pair: PairConfig) -> bool:
    block = pair.filters.keywords_block
    allow = pair.filters.keywords_allow
    lowered = text.lower() if text else ""

    if block and any(kw.lower() in lowered for kw in block):
        return False

    if allow:
        if not text:
            return False
        return any(kw.lower() in lowered for kw in allow)

    return True
