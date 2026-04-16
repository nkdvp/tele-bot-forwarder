from __future__ import annotations
import json
import os
import tempfile
from datetime import date


def _week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


class StatsCounter:
    def __init__(self, path: str = "data/stats.json"):
        self._path = path
        self._data: dict = {}
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def increment(self, pair_name: str) -> None:
        today = date.today()
        today_str = today.isoformat()
        today_week = _week_key(today)

        if pair_name not in self._data:
            self._data[pair_name] = {
                "date": today_str,
                "week_key": today_week,
                "today": 0,
                "week": 0,
            }

        entry = self._data[pair_name]

        if entry.get("date") != today_str:
            entry["today"] = 0
            entry["date"] = today_str

        if entry.get("week_key") != today_week:
            entry["week"] = 0
            entry["week_key"] = today_week

        entry["today"] += 1
        entry["week"] += 1
        self._save()

    def query(self, pair_name: str) -> dict:
        """Return {"today": N, "week": N}. Returns zeros if pair not found."""
        if pair_name not in self._data:
            return {"today": 0, "week": 0}
        entry = self._data[pair_name]
        today = date.today()
        today_str = today.isoformat()
        today_week = _week_key(today)
        today_count = entry.get("today", 0)
        week_count = entry.get("week", 0)
        if entry.get("date") != today_str:
            today_count = 0
        if entry.get("week_key") != today_week:
            week_count = 0
        return {"today": today_count, "week": week_count}

    def _save(self) -> None:
        dir_path = os.path.dirname(self._path) or "."
        os.makedirs(dir_path, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_path)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
