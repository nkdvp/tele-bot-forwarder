from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import Config
from bot.config.writer import save_and_reload, save_config
from bot.config.loader import _parse_pair
from bot.stats.counter import StatsCounter

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
        config._raw.setdefault("masking", {}).setdefault("users", {})[str(user_id)] = {
            "alias": alias_value
        }
    else:
        raw = _find_pair_raw(config, pair_name)
        if not raw:
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        raw.setdefault("masking", {}).setdefault(direction, {})[str(user_id)] = {
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
        users.pop(str(user_id), None)
    else:
        raw = _find_pair_raw(config, pair_name)
        if not raw:
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        raw.get("masking", {}).get(direction, {}).pop(str(user_id), None)

    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Masking removed for user {user_id}.")


async def cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /set recovery_window <minutes>
      /set alert_chat <chat_id>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage:\n/set recovery_window <minutes>\n/set alert_chat <chat_id>")
        return

    key, value = args[0], args[1]

    if key == "recovery_window":
        try:
            minutes = int(value)
        except ValueError:
            await update.message.reply_text("Invalid value. Usage: /set recovery_window <minutes>")
            return
        config._raw["recovery_window_minutes"] = minutes
        save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Recovery window set to {minutes} minutes.")

    elif key == "alert_chat":
        try:
            chat_id = int(value)
        except ValueError:
            await update.message.reply_text("Invalid value. Usage: /set alert_chat <chat_id>")
            return
        config._raw.setdefault("monitoring", {})["alert_chat_id"] = chat_id
        save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Alert chat set to {chat_id}.")

    else:
        await update.message.reply_text("Unknown key. Available: recovery_window, alert_chat")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /admin add <user_id>
      /admin remove <user_id>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if not args or args[0] not in ("add", "remove"):
        await update.message.reply_text("Usage:\n/admin add <user_id>\n/admin remove <user_id>")
        return

    action = args[0]
    if len(args) < 2:
        await update.message.reply_text(f"Usage: /admin {action} <user_id>")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    if action == "add":
        if user_id not in config._raw.get("admins", []):
            config._raw.setdefault("admins", []).append(user_id)
            save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Admin {user_id} added.")

    elif action == "remove":
        caller_id = update.effective_user.id
        if len(config.admins) <= 1:
            await update.message.reply_text("Cannot remove the last admin.")
            return
        if user_id == caller_id:
            await update.message.reply_text("Cannot remove yourself.")
            return
        if user_id in config._raw.get("admins", []):
            config._raw["admins"].remove(user_id)
            save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Admin {user_id} removed.")


_DEFAULT_PAIR_TYPES = ["text", "photo", "video", "sticker", "document", "voice", "animation"]


async def cmd_pair(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /pair add <name> <group_a_id> <group_b_id> [true|false]
      /pair remove <name>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if not args or args[0] not in ("add", "remove"):
        await update.message.reply_text(
            "Usage:\n"
            "/pair add <name> <group_a_id> <group_b_id> [true|false]\n"
            "/pair remove <name>"
        )
        return

    action = args[0]

    if action == "add":
        if len(args) < 4:
            await update.message.reply_text(
                "Usage: /pair add <name> <group_a_id> <group_b_id> [true|false]"
            )
            return
        name = args[1]
        try:
            group_a_id = int(args[2])
            group_b_id = int(args[3])
        except ValueError:
            await update.message.reply_text("Invalid chat ID.")
            return
        bidirectional = True
        if len(args) >= 5:
            bidirectional = args[4].lower() != "false"
        if any(p.name == name for p in config.pairs):
            await update.message.reply_text(f"Pair '{name}' already exists.")
            return
        new_pair = {
            "name": name,
            "group_a_chat_id": group_a_id,
            "group_b_chat_id": group_b_id,
            "bidirectional": bidirectional,
            "enabled": True,
            "filters": {
                "types": {"allow": _DEFAULT_PAIR_TYPES},
                "keywords": {"block": [], "allow": []},
            },
            "masking": {"a_to_b": {}, "b_to_a": {}},
        }
        config._raw.setdefault("pairs", []).append(new_pair)
        save_and_reload(config, CONFIG_PATH)
        bidir_str = "bidirectional" if bidirectional else "one-way"
        await update.message.reply_text(f"Pair '{name}' added ({bidir_str}).")

    elif action == "remove":
        if len(args) < 2:
            await update.message.reply_text("Usage: /pair remove <name>")
            return
        name = args[1]
        if not any(p.name == name for p in config.pairs):
            await update.message.reply_text(f"Pair '{name}' not found.")
            return
        config._raw["pairs"] = [p for p in config._raw.get("pairs", []) if p["name"] != name]
        save_config(config, CONFIG_PATH)
        config.pairs = [_parse_pair(p) for p in config._raw.get("pairs", [])]
        await update.message.reply_text(f"Pair '{name}' removed.")


async def cmd_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config: Config,
    stats: StatsCounter,
) -> None:
    """
    Usage:
      /stats
      /stats <pair-name>
    """
    if not _is_admin(update.effective_user.id, config):
        return

    if context.args:
        pair_name = context.args[0]
        if not any(p.name == pair_name for p in config.pairs):
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        counts = stats.query(pair_name)
        text = f"*Stats*\n\n{pair_name}: {counts['today']} today, {counts['week']} this week"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        lines = ["*Stats*\n"]
        for pair in config.pairs:
            counts = stats.query(pair.name)
            lines.append(f"{pair.name}: {counts['today']} today, {counts['week']} this week")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
