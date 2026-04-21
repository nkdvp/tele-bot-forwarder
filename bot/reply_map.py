from __future__ import annotations
import json
import os


class ReplyMap:
    def __init__(self, path: str = "data/reply_map.json"):
        self._path = path
        self._data: dict[str, list[int]] = {}
        if os.path.exists(path):
            with open(path, "r") as f:
                self._data = json.load(f)

    def record(self, src_chat: int, src_msg: int, dst_chat: int, dst_msg: int) -> None:
        self._data[f"{src_chat}:{src_msg}"] = [dst_chat, dst_msg]
        self._data[f"{dst_chat}:{dst_msg}"] = [src_chat, src_msg]
        self._save()

    def lookup(self, chat_id: int, msg_id: int) -> tuple[int, int] | None:
        entry = self._data.get(f"{chat_id}:{msg_id}")
        if entry is None:
            return None
        return (entry[0], entry[1])

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f)
