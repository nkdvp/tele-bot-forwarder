from __future__ import annotations
import logging
import os
from functools import partial
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, CommandHandler, filters
from bot.config.loader import load_config
from bot.masking.engine import MaskStore
from bot.handlers.message import handle_message
from bot.handlers.commands import (
    cmd_status,
    cmd_enable,
    cmd_disable,
    cmd_filter,
    cmd_mask,
    cmd_unmask,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    token = os.environ["BOT_TOKEN"]
    config = load_config("config.yaml")
    store = MaskStore("data/masks.json")

    app = Application.builder().token(token).build()

    # Message handler — receives all group/supergroup messages
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            partial(handle_message, config=config, store=store),
        )
    )

    # Admin command handlers
    app.add_handler(CommandHandler("status", partial(cmd_status, config=config)))
    app.add_handler(CommandHandler("enable", partial(cmd_enable, config=config)))
    app.add_handler(CommandHandler("disable", partial(cmd_disable, config=config)))
    app.add_handler(CommandHandler("filter", partial(cmd_filter, config=config)))
    app.add_handler(CommandHandler("mask", partial(cmd_mask, config=config)))
    app.add_handler(CommandHandler("unmask", partial(cmd_unmask, config=config)))

    logger.info("Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
