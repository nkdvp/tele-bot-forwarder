from __future__ import annotations
import re
import logging
from telegram import Message
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r'(?<!\w)@[A-Za-z0-9_]+')


def strip_mentions(text: str) -> str:
    result = re.sub(_MENTION_RE, '', text)
    return ' '.join(result.split())


async def forward_message(
    message: Message,
    display_name: str,
    dest_chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    try:
        if message.text:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name}: {message.text}",
            )

        elif message.photo:
            caption = f"{display_name}: {message.caption}" if message.caption else None
            header = None if caption else f"[photo sent by {display_name}]"
            if header:
                await context.bot.send_message(chat_id=dest_chat_id, text=header)
            await context.bot.send_photo(
                chat_id=dest_chat_id,
                photo=message.photo[-1].file_id,
                caption=caption,
            )

        elif message.video:
            caption = f"{display_name}: {message.caption}" if message.caption else None
            header = None if caption else f"[video sent by {display_name}]"
            if header:
                await context.bot.send_message(chat_id=dest_chat_id, text=header)
            await context.bot.send_video(
                chat_id=dest_chat_id,
                video=message.video.file_id,
                caption=caption,
            )

        elif message.document:
            caption = f"{display_name}: {message.caption}" if message.caption else None
            header = None if caption else f"[file sent by {display_name}]"
            if header:
                await context.bot.send_message(chat_id=dest_chat_id, text=header)
            await context.bot.send_document(
                chat_id=dest_chat_id,
                document=message.document.file_id,
                caption=caption,
            )

        elif message.voice:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a voice message:",
            )
            await context.bot.send_voice(
                chat_id=dest_chat_id,
                voice=message.voice.file_id,
            )

        elif message.sticker:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a sticker:",
            )
            await context.bot.send_sticker(
                chat_id=dest_chat_id,
                sticker=message.sticker.file_id,
            )

        elif message.animation:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a GIF:",
            )
            await context.bot.send_animation(
                chat_id=dest_chat_id,
                animation=message.animation.file_id,
            )

    except RetryAfter:
        raise  # let AIORateLimiter handle the retry
    except Exception as e:
        logger.error(
            "Failed to forward message to %s from %s: %s",
            dest_chat_id,
            display_name,
            e,
        )
