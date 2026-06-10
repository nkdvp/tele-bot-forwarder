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
from bot.runtime.storage_mode import build_storage_dependencies, use_db_config_mode
from bot.storage.auth_store import AuthStore
from bot.storage.backup_ops import run_backup_scheduler
from bot.web.admin_app import create_admin_app
from bot.web.server import run_admin_server
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
    admin_port = int(os.environ.get("ADMIN_PORT", "8090"))
    admin_host = os.environ.get("ADMIN_HOST", "0.0.0.0")
    db_path = os.environ.get("DB_PATH", "data/forwarder.db")
    use_db = use_db_config_mode(os.environ.get("USE_DB_CONFIG"))
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "change-me")
    backup_dir = os.environ.get("BACKUP_DIR", "backups")
    backup_retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
    backup_interval_seconds = int(os.environ.get("BACKUP_INTERVAL_SECONDS", "86400"))
    config = load_config("config.yaml")
    store = MaskStore("data/masks.json")
    stats = StatsCounter("data/stats.json")
    storage = build_storage_dependencies(
        use_db=use_db,
        db_path=db_path,
        reply_map_path="data/reply_map.json",
    )
    reply_map = storage.reply_link_store

    async def post_init(app: Application) -> None:
        task = asyncio.create_task(run_health_server(port=health_port))
        app.bot_data["_health_task"] = task
        app.bot_data["config_store"] = storage.config_store
        app.bot_data["use_db_config"] = use_db
        if use_db and storage.config_store is not None:
            auth_store = AuthStore(db_path)
            auth_store.ensure_admin_user(admin_username, admin_password)
            admin_app = create_admin_app(
                db_path=db_path,
                config_store=storage.config_store,
                auth_store=auth_store,
                backup_dir=backup_dir,
                backup_retention_days=backup_retention_days,
            )
            app.bot_data["_admin_task"] = asyncio.create_task(
                run_admin_server(app=admin_app, host=admin_host, port=admin_port)
            )
            app.bot_data["_backup_task"] = asyncio.create_task(
                run_backup_scheduler(
                    db_path=db_path,
                    backup_dir=backup_dir,
                    retention_days=backup_retention_days,
                    interval_seconds=backup_interval_seconds,
                )
            )
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
        admin_task = app.bot_data.get("_admin_task")
        if admin_task:
            admin_task.cancel()
        backup_task = app.bot_data.get("_backup_task")
        if backup_task:
            backup_task.cancel()
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
        .rate_limiter(AIORateLimiter(max_retries=3))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Message forwarding pipeline
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            partial(
                handle_message,
                config=config,
                store=store,
                stats=stats,
                reply_map=reply_map,
                config_store=storage.config_store,
            ),
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
    app.add_handler(
        CommandHandler(
            "enable",
            partial(cmd_enable, config=config, allow_mutations=not use_db),
        )
    )
    app.add_handler(
        CommandHandler(
            "disable",
            partial(cmd_disable, config=config, allow_mutations=not use_db),
        )
    )
    app.add_handler(
        CommandHandler(
            "filter",
            partial(cmd_filter, config=config, allow_mutations=not use_db),
        )
    )
    app.add_handler(
        CommandHandler(
            "mask",
            partial(cmd_mask, config=config, allow_mutations=not use_db),
        )
    )
    app.add_handler(
        CommandHandler(
            "unmask",
            partial(cmd_unmask, config=config, allow_mutations=not use_db),
        )
    )

    # New v2 commands
    app.add_handler(
        CommandHandler(
            "set",
            partial(cmd_set, config=config, allow_mutations=not use_db),
        )
    )
    app.add_handler(
        CommandHandler(
            "admin",
            partial(cmd_admin, config=config, allow_mutations=not use_db),
        )
    )
    app.add_handler(
        CommandHandler(
            "pair",
            partial(cmd_pair, config=config, allow_mutations=not use_db),
        )
    )
    app.add_handler(
        CommandHandler("stats", partial(cmd_stats, config=config, stats=stats))
    )

    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
