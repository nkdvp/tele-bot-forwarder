import pytest
from bot.filters.keyword_filter import passes_keyword_filter
from bot.config.loader import PairConfig, FilterConfig, PairMaskingConfig


def _make_pair(block: list[str], allow: list[str]) -> PairConfig:
    return PairConfig(
        name="p",
        group_a_chat_id=-1,
        group_b_chat_id=-2,
        bidirectional=True,
        enabled=True,
        filters=FilterConfig(
            types_allow=["text"],
            keywords_block=block,
            keywords_allow=allow,
        ),
        masking=PairMaskingConfig(a_to_b={}, b_to_a={}),
    )


def test_no_filters_passes():
    pair = _make_pair(block=[], allow=[])
    assert passes_keyword_filter("any message", pair) is True


def test_blocklist_blocks_matching_message():
    pair = _make_pair(block=["spam"], allow=[])
    assert passes_keyword_filter("this is spam here", pair) is False


def test_blocklist_passes_non_matching():
    pair = _make_pair(block=["spam"], allow=[])
    assert passes_keyword_filter("hello everyone", pair) is True


def test_allowlist_passes_matching():
    pair = _make_pair(block=[], allow=["urgent"])
    assert passes_keyword_filter("this is urgent", pair) is True


def test_allowlist_blocks_non_matching():
    pair = _make_pair(block=[], allow=["urgent"])
    assert passes_keyword_filter("hello everyone", pair) is False


def test_blocklist_takes_priority_over_allowlist():
    pair = _make_pair(block=["spam"], allow=["spam"])
    assert passes_keyword_filter("spam", pair) is False


def test_none_text_passes_with_no_allowlist():
    pair = _make_pair(block=[], allow=[])
    assert passes_keyword_filter(None, pair) is True


def test_none_text_blocked_when_allowlist_set():
    pair = _make_pair(block=[], allow=["urgent"])
    assert passes_keyword_filter(None, pair) is False


def test_keyword_match_is_case_insensitive():
    pair = _make_pair(block=["SPAM"], allow=[])
    assert passes_keyword_filter("this is spam", pair) is False
