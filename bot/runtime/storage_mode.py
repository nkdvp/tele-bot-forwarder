from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bot.reply_map import ReplyMap
from bot.storage.config_store import SQLiteConfigStore
from bot.storage.reply_link_store import SQLiteReplyLinkStore
from bot.storage.sqlite_db import initialize_database


class ReplyLinkStore(Protocol):
    def lookup(self, chat_id: int, msg_id: int) -> tuple[int, int] | None:
        ...

    def record(self, src_chat: int, src_msg: int, dst_chat: int, dst_msg: int) -> None:
        ...


@dataclass
class StorageDependencies:
    config_store: SQLiteConfigStore | None
    reply_link_store: ReplyLinkStore


def use_db_config_mode(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def build_storage_dependencies(
    *, use_db: bool, db_path: str, reply_map_path: str
) -> StorageDependencies:
    if use_db:
        initialize_database(db_path)
        return StorageDependencies(
            config_store=SQLiteConfigStore(db_path),
            reply_link_store=SQLiteReplyLinkStore(db_path),
        )

    return StorageDependencies(
        config_store=None,
        reply_link_store=ReplyMap(reply_map_path),
    )
