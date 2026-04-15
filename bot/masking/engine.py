from __future__ import annotations
import json
import os
from bot.config.loader import Config, PairConfig


class MaskStore:
    def __init__(self, path: str = "data/masks.json"):
        self._path = path
        self._data: dict[str, dict[str, int]] = {}
        if os.path.exists(path):
            with open(path, "r") as f:
                self._data = json.load(f)

    def get_anon_number(self, pair_name: str, user_id: int) -> int:
        key = str(user_id)
        if pair_name not in self._data:
            self._data[pair_name] = {}
        if key not in self._data[pair_name]:
            self._data[pair_name][key] = len(self._data[pair_name]) + 1
            self._save()
        return self._data[pair_name][key]

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)


def resolve_display_name(
    user_id: int,
    first_name: str,
    pair: PairConfig,
    direction: str,  # "a_to_b" or "b_to_a"
    config: Config,
    store: MaskStore,
) -> str:
    # 1. Per-pair directional override
    dir_masking = pair.masking.a_to_b if direction == "a_to_b" else pair.masking.b_to_a
    if user_id in dir_masking:
        entry = dir_masking[user_id]
        if entry.get("alias") is not None:
            return entry["alias"]
        return f"User #{store.get_anon_number(pair.name, user_id)}"

    # 2. Global masking
    if user_id in config.masking.users:
        entry = config.masking.users[user_id]
        if entry.get("alias") is not None:
            return entry["alias"]
        return f"User #{store.get_anon_number(pair.name, user_id)}"

    # 3. Real name
    return first_name
