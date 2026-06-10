from __future__ import annotations
import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import (
    Config,
    FilterConfig,
    PairConfig,
    PairMaskingConfig,
)
from bot.filters.type_filter import passes_type_filter
from bot.filters.keyword_filter import passes_keyword_filter
from bot.masking.engine import resolve_display_name, MaskStore
from bot.forwarder.relay import forward_message
from bot.reply_map import ReplyMap
from bot.stats.counter import StatsCounter
from bot.storage.config_store import SQLiteConfigStore, PairRecord

logger = logging.getLogger(__name__)


def _find_pair_and_direction(
    chat_id: int, config: Config
) -> tuple[PairConfig, str] | tuple[None, None]:
    for pair in config.pairs:
        if chat_id == pair.group_a_chat_id:
            return pair, "a_to_b"
        if pair.bidirectional and chat_id == pair.group_b_chat_id:
            return pair, "b_to_a"
    return None, None


def _store_pair_to_runtime_pair(pair: PairRecord) -> PairConfig:
    return PairConfig(
        name=pair.name,
        group_a_chat_id=pair.group_a_chat_id,
        group_b_chat_id=pair.group_b_chat_id,
        bidirectional=pair.bidirectional,
        enabled=pair.enabled,
        filters=FilterConfig(
            types_allow=pair.filters.types_allow,
            keywords_block=pair.filters.keywords_block,
            keywords_allow=pair.filters.keywords_allow,
        ),
        masking=PairMaskingConfig(a_to_b={}, b_to_a={}),
    )


def _find_pair_and_direction_from_store(
    chat_id: int, config_store: SQLiteConfigStore
) -> tuple[PairConfig, str] | tuple[None, None]:
    matches = config_store.list_pairs(chat_id=chat_id)
    for pair in matches:
        if chat_id == pair.group_a_chat_id:
            return _store_pair_to_runtime_pair(pair), "a_to_b"
        if pair.bidirectional and chat_id == pair.group_b_chat_id:
            return _store_pair_to_runtime_pair(pair), "b_to_a"
    return None, None


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config: Config,
    store: MaskStore,
    stats: StatsCounter,
    reply_map: ReplyMap,
    config_store: SQLiteConfigStore | None = None,
) -> None:
    message = update.effective_message
    if not message or not message.from_user:
        return

    # Loop prevention: drop messages sent by the bot itself
    if message.from_user.id == context.bot.id:
        return

    # Age filter — skip stale messages buffered during downtime
    if config.recovery_window_minutes > 0:
        msg_date = message.date
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - msg_date).total_seconds()
        if age > config.recovery_window_minutes * 60:
            logger.info(
                "Skipping stale message %.0fs old (limit %dm)",
                age,
                config.recovery_window_minutes,
            )
            return

    chat_id = update.effective_chat.id
    if config_store is not None:
        pair, direction = _find_pair_and_direction_from_store(chat_id, config_store)
    else:
        pair, direction = _find_pair_and_direction(chat_id, config)
    if pair is None:
        return

    if not pair.enabled:
        return

    if not passes_type_filter(message, pair):
        return

    text = message.text or message.caption
    if not passes_keyword_filter(text, pair):
        return

    sender = message.from_user
    display_name = resolve_display_name(
        sender.id,
        sender.first_name or "Unknown",
        pair,
        direction,
        config,
        store,
    )

    dest_chat_id = pair.group_b_chat_id if direction == "a_to_b" else pair.group_a_chat_id
    await forward_message(message, display_name, dest_chat_id, context, reply_map, config)
    stats.increment(pair.name)
