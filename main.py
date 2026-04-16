from __future__ import annotations
import asyncio
import logging
import os
from functools import partial
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ChatMemberHandler,
    filters,
    AIORateLimiter,
)
from bot.config.loader import load_config
from bot.masking.engine import MaskStore
from bot.stats.counter import StatsCounter
from bot.health.server import run_health_server
from bot.handlers.message import handle_message
from bot.handlers.membership import handle_bot_added
from bot.handlers.commands import (
    cmd_status,
    cmd_enable,
    cmd_disable,
    cmd_filter,
    cmd_mask,
    cmd_unmask,
    cmd_set,
    cmd_admin,
    cmd_pair,
    cmd_stats,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    token = os.environ["BOT_TOKEN"]
    health_port = int(os.environ.get("HEALTH_PORT", "8080"))
    config = load_config("config.yaml")
    store = MaskStore("data/masks.json")
    stats = StatsCounter("data/stats.json")

    async def post_init(app: Application) -> None:
        task = asyncio.create_task(run_health_server(port=health_port))
        app.bot_data["_health_task"] = task
        await app.bot.set_my_commands([
            BotCommand("status", "Show all pairs and their state"),
            BotCommand("enable", "Enable a pair: /enable <pair>"),
            BotCommand("disable", "Disable a pair: /disable <pair>"),
            BotCommand("stats", "Message counts: /stats [pair]"),
            BotCommand("pair", "Manage pairs: /pair add|remove ..."),
            BotCommand("set", "Change settings: /set recovery_window|alert_chat <value>"),
            BotCommand("admin", "Manage admins: /admin add|remove <user_id>"),
            BotCommand("filter", "Edit filters: /filter <pair> block|allow|remove type|keyword <value>"),
            BotCommand("mask", "Set sender alias: /mask <pair> a_to_b|b_to_a|global <user_id> <alias|anon>"),
            BotCommand("unmask", "Remove alias: /unmask <pair> a_to_b|b_to_a|global <user_id>"),
        ])
        if config.monitoring and config.monitoring.alert_chat_id:
            try:
                await app.bot.send_message(
                    chat_id=config.monitoring.alert_chat_id, text="Bot started"
                )
            except Exception as e:
                logger.warning("Could not send startup alert: %s", e)

    async def post_shutdown(app: Application) -> None:
        task = app.bot_data.get("_health_task")
        if task:
            task.cancel()
        if config.monitoring and config.monitoring.alert_chat_id:
            try:
                await app.bot.send_message(
                    chat_id=config.monitoring.alert_chat_id, text="Bot stopping"
                )
            except Exception as e:
                logger.warning("Could not send shutdown alert: %s", e)

    app = (
        Application.builder()
        .token(token)
        .rate_limiter(AIORateLimiter())
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Message forwarding pipeline
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            partial(handle_message, config=config, store=store, stats=stats),
        )
    )

    # Group membership events — auto group ID discovery
    app.add_handler(
        ChatMemberHandler(
            partial(handle_bot_added, config=config),
            ChatMemberHandler.MY_CHAT_MEMBER,
        )
    )

    # Existing v1 commands
    app.add_handler(CommandHandler("status", partial(cmd_status, config=config)))
    app.add_handler(CommandHandler("enable", partial(cmd_enable, config=config)))
    app.add_handler(CommandHandler("disable", partial(cmd_disable, config=config)))
    app.add_handler(CommandHandler("filter", partial(cmd_filter, config=config)))
    app.add_handler(CommandHandler("mask", partial(cmd_mask, config=config)))
    app.add_handler(CommandHandler("unmask", partial(cmd_unmask, config=config)))

    # New v2 commands
    app.add_handler(CommandHandler("set", partial(cmd_set, config=config)))
    app.add_handler(CommandHandler("admin", partial(cmd_admin, config=config)))
    app.add_handler(CommandHandler("pair", partial(cmd_pair, config=config)))
    app.add_handler(
        CommandHandler("stats", partial(cmd_stats, config=config, stats=stats))
    )

    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
