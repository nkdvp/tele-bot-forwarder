from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import Config
from bot.config.writer import save_and_reload

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


def _is_admin(user_id: int, config: Config) -> bool:
    return user_id in config.admins


def _find_pair_raw(config: Config, pair_name: str) -> dict | None:
    for p in config._raw.get("pairs", []):
        if p["name"] == pair_name:
            return p
    return None


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    if not _is_admin(update.effective_user.id, config):
        return
    lines = ["*Forwarding Pairs Status*"]
    for pair in config.pairs:
        state = "enabled" if pair.enabled else "disabled"
        direction = "bidirectional" if pair.bidirectional else "one-way (A→B)"
        lines.append(
            f"\n*{pair.name}* — {state}, {direction}\n"
            f"  A: `{pair.group_a_chat_id}`\n"
            f"  B: `{pair.group_b_chat_id}`\n"
            f"  Types: {', '.join(pair.filters.types_allow)}\n"
            f"  Block keywords: {pair.filters.keywords_block or 'none'}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_enable(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    if not _is_admin(update.effective_user.id, config):
        return
    if not context.args:
        await update.message.reply_text("Usage: /enable <pair-name>")
        return
    pair_name = context.args[0]
    raw = _find_pair_raw(config, pair_name)
    if not raw:
        await update.message.reply_text(f"Pair '{pair_name}' not found.")
        return
    raw["enabled"] = True
    for pair in config.pairs:
        if pair.name == pair_name:
            pair.enabled = True
    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Pair '{pair_name}' enabled.")


async def cmd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    if not _is_admin(update.effective_user.id, config):
        return
    if not context.args:
        await update.message.reply_text("Usage: /disable <pair-name>")
        return
    pair_name = context.args[0]
    raw = _find_pair_raw(config, pair_name)
    if not raw:
        await update.message.reply_text(f"Pair '{pair_name}' not found.")
        return
    raw["enabled"] = False
    for pair in config.pairs:
        if pair.name == pair_name:
            pair.enabled = False
    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Pair '{pair_name}' disabled.")


async def cmd_filter(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /filter <pair> block type <type>
      /filter <pair> allow type <type>
      /filter <pair> block keyword <word>
      /filter <pair> allow keyword <word>
      /filter <pair> remove keyword <word>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: /filter <pair> <block|allow|remove> <type|keyword> <value>"
        )
        return

    pair_name, action, category, value = args[0], args[1], args[2], args[3]
    raw = _find_pair_raw(config, pair_name)
    if not raw:
        await update.message.reply_text(f"Pair '{pair_name}' not found.")
        return

    filters = raw.setdefault("filters", {})
    if category == "type":
        types_allow = filters.setdefault("types", {}).setdefault("allow", [])
        if action == "allow" and value not in types_allow:
            types_allow.append(value)
        elif action == "block" and value in types_allow:
            types_allow.remove(value)
        elif action == "remove" and value in types_allow:
            types_allow.remove(value)
    elif category == "keyword":
        keywords = filters.setdefault("keywords", {})
        block_list = keywords.setdefault("block", [])
        allow_list = keywords.setdefault("allow", [])
        if action == "block" and value not in block_list:
            block_list.append(value)
        elif action == "allow" and value not in allow_list:
            allow_list.append(value)
        elif action == "remove":
            if value in block_list:
                block_list.remove(value)
            if value in allow_list:
                allow_list.remove(value)
    else:
        await update.message.reply_text("Category must be 'type' or 'keyword'.")
        return

    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Filter updated for '{pair_name}'.")


async def cmd_mask(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage: /mask <pair> <a_to_b|b_to_a|global> <user_id> <alias|anon>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: /mask <pair> <a_to_b|b_to_a|global> <user_id> <alias|anon>"
        )
        return

    pair_name, direction, user_id_str, alias = args[0], args[1], args[2], " ".join(args[3:])
    try:
        user_id = int(user_id_str)
    except ValueError:
        await update.message.reply_text("user_id must be a number.")
        return

    alias_value = None if alias.lower() == "anon" else alias

    if direction == "global":
        config._raw.setdefault("masking", {}).setdefault("users", {})[user_id] = {
            "alias": alias_value
        }
    else:
        raw = _find_pair_raw(config, pair_name)
        if not raw:
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        raw.setdefault("masking", {}).setdefault(direction, {})[user_id] = {
            "alias": alias_value
        }

    save_and_reload(config, CONFIG_PATH)
    label = "anonymous" if alias_value is None else f'"{alias_value}"'
    await update.message.reply_text(f"User {user_id} will now appear as {label}.")


async def cmd_unmask(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage: /unmask <pair> <a_to_b|b_to_a|global> <user_id>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /unmask <pair> <a_to_b|b_to_a|global> <user_id>"
        )
        return

    pair_name, direction, user_id_str = args[0], args[1], args[2]
    try:
        user_id = int(user_id_str)
    except ValueError:
        await update.message.reply_text("user_id must be a number.")
        return

    if direction == "global":
        users = config._raw.get("masking", {}).get("users", {})
        users.pop(user_id, None)
    else:
        raw = _find_pair_raw(config, pair_name)
        if not raw:
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        raw.get("masking", {}).get(direction, {}).pop(user_id, None)

    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Masking removed for user {user_id}.")
