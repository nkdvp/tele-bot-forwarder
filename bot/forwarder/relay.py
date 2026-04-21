from __future__ import annotations
import re
import logging
from telegram import Message
from telegram.error import RetryAfter
from telegram.ext import ContextTypes
from bot.reply_map import ReplyMap
from bot.config.loader import Config

logger = logging.getLogger(__name__)

# [A-Za-z0-9_] matches Telegram's username charset; \w would also strip Unicode non-mentions.
_MENTION_RE = re.compile(r'(?<!\w)@[A-Za-z0-9_]+')


def strip_mentions(text: str) -> str:
    result = re.sub(_MENTION_RE, '', text)
    return ' '.join(result.split())


async def forward_message(
    message: Message,
    display_name: str,
    dest_chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_map: ReplyMap,
    config: Config,
) -> None:
    src_chat_id = message.chat.id
    src_msg_id = message.message_id

    reply_to_id: int | None = None
    if message.reply_to_message:
        result = reply_map.lookup(src_chat_id, message.reply_to_message.message_id)
        if result is not None:
            _, reply_to_id = result

    def clean(text: str | None) -> str | None:
        if text is None:
            return None
        return strip_mentions(text) if config.strip_mentions else text

    sent = None
    try:
        if message.text:
            sent = await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name}: {clean(message.text)}",
                reply_to_message_id=reply_to_id,
            )

        elif message.photo:
            caption = f"{display_name}: {clean(message.caption)}" if message.caption else None
            header = None if caption else f"[photo sent by {display_name}]"
            if header:
                await context.bot.send_message(
                    chat_id=dest_chat_id,
                    text=header,
                    reply_to_message_id=reply_to_id,
                )
            sent = await context.bot.send_photo(
                chat_id=dest_chat_id,
                photo=message.photo[-1].file_id,
                caption=caption,
                reply_to_message_id=reply_to_id if caption else None,
            )

        elif message.video:
            caption = f"{display_name}: {clean(message.caption)}" if message.caption else None
            header = None if caption else f"[video sent by {display_name}]"
            if header:
                await context.bot.send_message(
                    chat_id=dest_chat_id,
                    text=header,
                    reply_to_message_id=reply_to_id,
                )
            sent = await context.bot.send_video(
                chat_id=dest_chat_id,
                video=message.video.file_id,
                caption=caption,
                reply_to_message_id=reply_to_id if caption else None,
            )

        elif message.document:
            caption = f"{display_name}: {clean(message.caption)}" if message.caption else None
            header = None if caption else f"[file sent by {display_name}]"
            if header:
                await context.bot.send_message(
                    chat_id=dest_chat_id,
                    text=header,
                    reply_to_message_id=reply_to_id,
                )
            sent = await context.bot.send_document(
                chat_id=dest_chat_id,
                document=message.document.file_id,
                caption=caption,
                reply_to_message_id=reply_to_id if caption else None,
            )

        elif message.voice:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a voice message:",
                reply_to_message_id=reply_to_id,
            )
            sent = await context.bot.send_voice(
                chat_id=dest_chat_id,
                voice=message.voice.file_id,
            )

        elif message.sticker:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a sticker:",
                reply_to_message_id=reply_to_id,
            )
            sent = await context.bot.send_sticker(
                chat_id=dest_chat_id,
                sticker=message.sticker.file_id,
            )

        elif message.animation:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a GIF:",
                reply_to_message_id=reply_to_id,
            )
            sent = await context.bot.send_animation(
                chat_id=dest_chat_id,
                animation=message.animation.file_id,
            )

    except RetryAfter:
        raise
    except Exception as e:
        logger.error(
            "Failed to forward message to %s from %s: %s",
            dest_chat_id,
            display_name,
            e,
        )

    # For two-send types (voice/sticker/animation), the header carries reply_to_id
    # and the media message_id is recorded so future reply lookups resolve correctly.
    if sent is not None:
        try:
            reply_map.record(src_chat_id, src_msg_id, dest_chat_id, sent.message_id)
        except Exception as e:
            logger.warning("Failed to record reply map entry: %s", e)
