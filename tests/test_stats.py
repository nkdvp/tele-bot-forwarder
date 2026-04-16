import pytest
import json
from datetime import date, timedelta
from unittest.mock import patch
from bot.stats.counter import StatsCounter


def test_query_unknown_pair_returns_zeros(tmp_path):
    stats = StatsCounter(str(tmp_path / "stats.json"))
    result = stats.query("nonexistent")
    assert result == {"today": 0, "week": 0}


def test_increment_creates_entry(tmp_path):
    stats = StatsCounter(str(tmp_path / "stats.json"))
    stats.increment("my-pair")
    result = stats.query("my-pair")
    assert result["today"] == 1
    assert result["week"] == 1


def test_increment_accumulates(tmp_path):
    stats = StatsCounter(str(tmp_path / "stats.json"))
    stats.increment("my-pair")
    stats.increment("my-pair")
    stats.increment("my-pair")
    assert stats.query("my-pair") == {"today": 3, "week": 3}


def test_increment_persists_to_disk(tmp_path):
    path = str(tmp_path / "stats.json")
    s1 = StatsCounter(path)
    s1.increment("my-pair")
    s2 = StatsCounter(path)
    assert s2.query("my-pair") == {"today": 1, "week": 1}


def test_day_rollover_resets_today_preserves_week(tmp_path):
    stats = StatsCounter(str(tmp_path / "stats.json"))
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    # Seed with yesterday's data
    stats._data["my-pair"] = {
        "date": yesterday,
        "week_key": _week_key(date.today()),  # same week
        "today": 10,
        "week": 50,
    }
    stats.increment("my-pair")
    result = stats.query("my-pair")
    assert result["today"] == 1     # reset + new increment
    assert result["week"] == 51     # accumulated


def test_week_rollover_resets_both(tmp_path):
    stats = StatsCounter(str(tmp_path / "stats.json"))
    last_week = _week_key(date.today() - timedelta(weeks=1))
    stats._data["my-pair"] = {
        "date": (date.today() - timedelta(days=8)).isoformat(),
        "week_key": last_week,
        "today": 5,
        "week": 100,
    }
    stats.increment("my-pair")
    result = stats.query("my-pair")
    assert result["today"] == 1
    assert result["week"] == 1


def _week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"
