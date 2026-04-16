from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import Config

logger = logging.getLogger(__name__)


async def handle_bot_added(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config: Config,
) -> None:
    chat_member = update.my_chat_member
    if not chat_member:
        return

    new_status = chat_member.new_chat_member.status
    if new_status not in ("member", "administrator"):
        return

    chat = chat_member.chat
    if chat.type not in ("group", "supergroup"):
        return

    if not config.admins:
        return

    chat_id = chat.id
    chat_name = chat.title or "Unknown"
    text = (
        f"Bot added to group:\n"
        f"Name: {chat_name}\n"
        f"Chat ID: {chat_id}\n\n"
        f"Use: /pair add <name> {chat_id} <other_group_id>"
    )

    try:
        await context.bot.send_message(chat_id=config.admins[0], text=text)
    except Exception as e:
        logger.warning("Could not DM admin on group join: %s", e)
