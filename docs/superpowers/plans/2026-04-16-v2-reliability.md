# Telegram Forwarder Bot v2 — Reliability & Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rate limiting, health monitoring, message recovery, runtime config/admin/pair commands, auto group discovery, and message stats to the existing Telegram forwarder bot.

**Architecture:** All changes are additive. The existing polling pipeline is unchanged. New features slot in via: (1) extended `Config` dataclass, (2) new `bot/health/` and `bot/stats/` modules, (3) new handlers in `bot/handlers/`, (4) updated `main.py` wiring. TDD throughout — write the failing test first, then the minimal implementation.

**Tech Stack:** Python 3.11+, `python-telegram-bot==21.6`, `aiohttp` (new), `PyYAML`, `pytest`, `pytest-asyncio`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `bot/config/loader.py` | Modify | Add `MonitoringConfig` dataclass; add `recovery_window_minutes` + `monitoring` to `Config` |
| `bot/config/writer.py` | Modify | Patch `save_and_reload` to sync new top-level fields |
| `bot/stats/__init__.py` | Create | Empty package marker |
| `bot/stats/counter.py` | Create | `StatsCounter` — `increment(pair)` / `query(pair)` backed by `data/stats.json` |
| `bot/health/__init__.py` | Create | Empty package marker |
| `bot/health/server.py` | Create | `run_health_server(port)` — aiohttp `GET /health` endpoint |
| `bot/handlers/message.py` | Modify | Add age filter; call `stats.increment` after successful relay |
| `bot/handlers/commands.py` | Modify | Add `cmd_set`, `cmd_admin`, `cmd_pair`, `cmd_stats` |
| `bot/handlers/membership.py` | Create | `handle_bot_added` — DM first admin when bot joins a group |
| `main.py` | Modify | Wire `AIORateLimiter`, `post_init`/`post_shutdown` hooks, all new handlers |
| `config.yaml` | Modify | Add `recovery_window_minutes` and `monitoring` block |
| `.env.example` | Modify | Add `HEALTH_PORT=8080` |
| `requirements.txt` | Modify | Add `aiohttp` |
| `deploy/DEPLOY.md` | Modify | Add firewall rule + UptimeRobot setup section |
| `tests/test_config_loader.py` | Modify | Extend with new field tests |
| `tests/test_stats.py` | Create | Unit tests for `StatsCounter` |
| `tests/test_health.py` | Create | Unit test for health handler |
| `tests/test_message_handler.py` | Create | Unit tests for age filter + stats increment |
| `tests/test_commands_v2.py` | Create | Unit tests for `/set`, `/admin`, `/pair`, `/stats` |
| `tests/test_membership.py` | Create | Unit test for group discovery DM |

---

## Task 1: Config loader — MonitoringConfig + recovery_window_minutes

**Files:**
- Modify: `bot/config/loader.py`
- Modify: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_loader.py`:

```python
def test_load_config_recovery_window_default(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    assert config.recovery_window_minutes == 15


def test_load_config_recovery_window_explicit(tmp_path):
    data = {**MINIMAL_CONFIG, "recovery_window_minutes": 30}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    assert config.recovery_window_minutes == 30


def test_load_config_monitoring_absent(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    assert config.monitoring is None


def test_load_config_monitoring_present(tmp_path):
    data = {**MINIMAL_CONFIG, "monitoring": {"alert_chat_id": 987654321}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    assert config.monitoring is not None
    assert config.monitoring.alert_chat_id == 987654321
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_loader.py::test_load_config_recovery_window_default \
       tests/test_config_loader.py::test_load_config_monitoring_present -v
```

Expected: FAIL with `AttributeError: 'Config' object has no attribute 'recovery_window_minutes'`

- [ ] **Step 3: Implement changes to `bot/config/loader.py`**

Replace the full file content:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import yaml


@dataclass
class FilterConfig:
    types_allow: list[str]
    keywords_block: list[str]
    keywords_allow: list[str]


@dataclass
class PairMaskingConfig:
    a_to_b: dict[int, dict]
    b_to_a: dict[int, dict]


@dataclass
class PairConfig:
    name: str
    group_a_chat_id: int
    group_b_chat_id: int
    bidirectional: bool
    enabled: bool
    filters: FilterConfig
    masking: PairMaskingConfig


@dataclass
class GlobalMaskingConfig:
    users: dict[int, dict]


@dataclass
class MonitoringConfig:
    alert_chat_id: int


@dataclass
class Config:
    admins: list[int]
    masking: GlobalMaskingConfig
    pairs: list[PairConfig]
    recovery_window_minutes: int = 15
    monitoring: MonitoringConfig | None = None
    _raw: dict = field(default_factory=dict, repr=False)


def _parse_pair(raw: dict) -> PairConfig:
    filters_raw = raw.get("filters", {})
    types_raw = filters_raw.get("types", {})
    keywords_raw = filters_raw.get("keywords", {})
    masking_raw = raw.get("masking", {})

    return PairConfig(
        name=raw["name"],
        group_a_chat_id=raw["group_a_chat_id"],
        group_b_chat_id=raw["group_b_chat_id"],
        bidirectional=raw.get("bidirectional", True),
        enabled=raw.get("enabled", True),
        filters=FilterConfig(
            types_allow=types_raw.get("allow", ["text"]),
            keywords_block=keywords_raw.get("block", []),
            keywords_allow=keywords_raw.get("allow", []),
        ),
        masking=PairMaskingConfig(
            a_to_b={int(k): v for k, v in (masking_raw.get("a_to_b") or {}).items()},
            b_to_a={int(k): v for k, v in (masking_raw.get("b_to_a") or {}).items()},
        ),
    )


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if "admins" not in raw or not raw["admins"]:
        raise ValueError("config.yaml must define at least one admin user ID under 'admins'")
    if "pairs" not in raw or not raw["pairs"]:
        raise ValueError("config.yaml must define at least one pair under 'pairs'")

    masking_raw = raw.get("masking", {})
    global_masking = GlobalMaskingConfig(
        users={int(k): v for k, v in (masking_raw.get("users") or {}).items()}
    )

    monitoring = None
    monitoring_raw = raw.get("monitoring")
    if monitoring_raw and monitoring_raw.get("alert_chat_id"):
        monitoring = MonitoringConfig(alert_chat_id=int(monitoring_raw["alert_chat_id"]))

    return Config(
        admins=[int(a) for a in raw["admins"]],
        masking=global_masking,
        pairs=[_parse_pair(p) for p in raw["pairs"]],
        recovery_window_minutes=int(raw.get("recovery_window_minutes", 15)),
        monitoring=monitoring,
        _raw=raw,
    )
```

- [ ] **Step 4: Run all config loader tests**

```bash
pytest tests/test_config_loader.py -v
```

Expected: All PASS (existing + 4 new tests)

- [ ] **Step 5: Commit**

```bash
git add bot/config/loader.py tests/test_config_loader.py
git commit -m "feat: add MonitoringConfig and recovery_window_minutes to Config"
```

---

## Task 2: Config writer patch — sync new fields in save_and_reload

**Files:**
- Modify: `bot/config/writer.py`
- Modify: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_loader.py`:

```python
def test_save_and_reload_syncs_recovery_window(tmp_path):
    data = {**MINIMAL_CONFIG, "recovery_window_minutes": 15}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    config._raw["recovery_window_minutes"] = 45
    save_and_reload(config, str(config_file))
    assert config.recovery_window_minutes == 45


def test_save_and_reload_syncs_monitoring(tmp_path):
    data = {**MINIMAL_CONFIG, "monitoring": {"alert_chat_id": 111}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    config._raw["monitoring"]["alert_chat_id"] = 999
    save_and_reload(config, str(config_file))
    assert config.monitoring.alert_chat_id == 999
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_loader.py::test_save_and_reload_syncs_recovery_window \
       tests/test_config_loader.py::test_save_and_reload_syncs_monitoring -v
```

Expected: FAIL — `assert config.recovery_window_minutes == 45` fails (still 15)

- [ ] **Step 3: Patch `bot/config/writer.py`**

```python
from __future__ import annotations
import yaml
from bot.config.loader import Config, load_config


def save_config(config: Config, path: str = "config.yaml") -> None:
    with open(path, "w") as f:
        yaml.dump(config._raw, f, default_flow_style=False, allow_unicode=True)


def save_and_reload(config: Config, path: str = "config.yaml") -> None:
    """Persist _raw to disk, then re-parse and update config in-place."""
    save_config(config, path)
    fresh = load_config(path)
    config.admins = fresh.admins
    config.masking = fresh.masking
    config.pairs = fresh.pairs
    config.recovery_window_minutes = fresh.recovery_window_minutes
    config.monitoring = fresh.monitoring
```

- [ ] **Step 4: Run all config loader tests**

```bash
pytest tests/test_config_loader.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/config/writer.py tests/test_config_loader.py
git commit -m "feat: patch save_and_reload to sync recovery_window_minutes and monitoring"
```

---

## Task 3: Stats counter

**Files:**
- Create: `bot/stats/__init__.py`
- Create: `bot/stats/counter.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_stats.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.stats'`

- [ ] **Step 3: Create `bot/stats/__init__.py`**

```python
```

(empty file)

- [ ] **Step 4: Create `bot/stats/counter.py`**

```python
from __future__ import annotations
import json
import os
from datetime import date


def _week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


class StatsCounter:
    def __init__(self, path: str = "data/stats.json"):
        self._path = path
        self._data: dict = {}
        if os.path.exists(path):
            with open(path, "r") as f:
                self._data = json.load(f)

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
        return {"today": entry.get("today", 0), "week": entry.get("week", 0)}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)
```

- [ ] **Step 5: Run stats tests**

```bash
pytest tests/test_stats.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add bot/stats/__init__.py bot/stats/counter.py tests/test_stats.py
git commit -m "feat: add StatsCounter backed by data/stats.json"
```

---

## Task 4: Health server

**Files:**
- Create: `bot/health/__init__.py`
- Create: `bot/health/server.py`
- Create: `tests/test_health.py`

- [ ] **Step 1: Add `aiohttp` to `requirements.txt`**

```
python-telegram-bot==21.6
PyYAML==6.0.2
python-dotenv==1.0.1
aiohttp==3.11.11
pytest==8.3.3
pytest-asyncio==0.24.0
```

Install it:

```bash
source venv/bin/activate && pip install aiohttp==3.11.11
```

Expected: `Successfully installed aiohttp-3.11.11 ...`

- [ ] **Step 2: Write the failing test**

Create `tests/test_health.py`:

```python
import pytest
import json
from unittest.mock import MagicMock
from bot.health.server import health_handler


@pytest.mark.asyncio
async def test_health_handler_returns_ok():
    request = MagicMock()
    response = await health_handler(request)
    assert response.status == 200
    body = json.loads(response.body)
    assert body["status"] == "ok"
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_health.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.health'`

- [ ] **Step 4: Create `bot/health/__init__.py`**

Empty file.

- [ ] **Step 5: Create `bot/health/server.py`**

```python
from __future__ import annotations
import asyncio
import time
from aiohttp import web

_start_time = time.monotonic()


async def health_handler(request: web.Request) -> web.Response:
    uptime = int(time.monotonic() - _start_time)
    return web.json_response({"status": "ok", "uptime_seconds": uptime})


async def run_health_server(port: int = 8080) -> None:
    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
    except OSError as e:
        import logging
        logging.getLogger(__name__).error("Health server failed to start on port %d: %s", port, e)
        await runner.cleanup()
        return
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
```

- [ ] **Step 6: Run health tests**

```bash
pytest tests/test_health.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add bot/health/__init__.py bot/health/server.py tests/test_health.py requirements.txt
git commit -m "feat: add aiohttp health server at GET /health"
```

---

## Task 5: Message handler — age filter + stats increment

**Files:**
- Modify: `bot/handlers/message.py`
- Create: `tests/test_message_handler.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_message_handler.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bot.handlers.message import handle_message
from bot.config.loader import (
    Config, GlobalMaskingConfig, PairConfig, FilterConfig, PairMaskingConfig
)


def _make_config(recovery_window_minutes: int = 15) -> Config:
    return Config(
        admins=[1],
        masking=GlobalMaskingConfig(users={}),
        pairs=[
            PairConfig(
                name="test-pair",
                group_a_chat_id=-100111,
                group_b_chat_id=-100222,
                bidirectional=True,
                enabled=True,
                filters=FilterConfig(
                    types_allow=["text"],
                    keywords_block=[],
                    keywords_allow=[],
                ),
                masking=PairMaskingConfig(a_to_b={}, b_to_a={}),
            )
        ],
        recovery_window_minutes=recovery_window_minutes,
        _raw={},
    )


def _make_update_and_context(age_seconds: int = 0, chat_id: int = -100111):
    message = MagicMock()
    message.from_user.id = 999
    message.from_user.first_name = "Tester"
    message.date = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    message.text = "hello"
    message.caption = None
    message.photo = None
    message.video = None
    message.document = None
    message.voice = None
    message.sticker = None
    message.animation = None

    update = MagicMock()
    update.effective_message = message
    update.effective_chat.id = chat_id

    context = MagicMock()
    context.bot.id = 1  # different from sender (999)

    return update, context


@pytest.mark.asyncio
async def test_age_filter_skips_stale_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=20 * 60)
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        await handle_message(update, context, config=config, store=store, stats=stats)

    mock_fwd.assert_not_called()
    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_age_filter_passes_recent_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=5 * 60)
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock):
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats)

    stats.increment.assert_called_once_with("test-pair")


@pytest.mark.asyncio
async def test_age_filter_disabled_when_zero():
    config = _make_config(recovery_window_minutes=0)
    update, context = _make_update_and_context(age_seconds=60 * 60)  # 1 hour old
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats)

    mock_fwd.assert_called_once()


@pytest.mark.asyncio
async def test_stats_not_incremented_when_message_dropped_by_filter():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context()
    # Pair is disabled
    config.pairs[0].enabled = False
    store = MagicMock()
    stats = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock):
        await handle_message(update, context, config=config, store=store, stats=stats)

    stats.increment.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_message_handler.py -v
```

Expected: FAIL — `handle_message() got unexpected keyword argument 'stats'`

- [ ] **Step 3: Update `bot/handlers/message.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import Config, PairConfig
from bot.filters.type_filter import passes_type_filter
from bot.filters.keyword_filter import passes_keyword_filter
from bot.masking.engine import resolve_display_name, MaskStore
from bot.forwarder.relay import forward_message
from bot.stats.counter import StatsCounter

logger = logging.getLogger(__name__)


def _find_pair_and_direction(
    chat_id: int, config: Config
) -> tuple[PairConfig, str] | tuple[None, None]:
    for pair in config.pairs:
        if chat_id == pair.group_a_chat_id:
            return pair, "a_to_b"
        if pair.bidirectional and chat_id == pair.group_b_chat_id:
            return pair, "b_to_a"
    return None, None


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config: Config,
    store: MaskStore,
    stats: StatsCounter,
) -> None:
    message = update.effective_message
    if not message or not message.from_user:
        return

    # Loop prevention: drop messages sent by the bot itself
    if message.from_user.id == context.bot.id:
        return

    # Age filter — skip stale messages buffered during downtime
    if config.recovery_window_minutes > 0:
        age = (datetime.now(timezone.utc) - message.date).total_seconds()
        if age > config.recovery_window_minutes * 60:
            logger.info(
                "Skipping stale message %.0fs old (limit %dm)",
                age,
                config.recovery_window_minutes,
            )
            return

    chat_id = update.effective_chat.id
    pair, direction = _find_pair_and_direction(chat_id, config)
    if pair is None:
        return

    if not pair.enabled:
        return

    if not passes_type_filter(message, pair):
        return

    text = message.text or message.caption
    if not passes_keyword_filter(text, pair):
        return

    sender = message.from_user
    display_name = resolve_display_name(
        sender.id,
        sender.first_name or "Unknown",
        pair,
        direction,
        config,
        store,
    )

    dest_chat_id = pair.group_b_chat_id if direction == "a_to_b" else pair.group_a_chat_id
    await forward_message(message, display_name, dest_chat_id, context)
    stats.increment(pair.name)
```

- [ ] **Step 4: Run message handler tests**

```bash
pytest tests/test_message_handler.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/message.py tests/test_message_handler.py
git commit -m "feat: add age filter and stats increment to message handler"
```

---

## Task 6: /set and /admin commands

**Files:**
- Modify: `bot/handlers/commands.py`
- Create: `tests/test_commands_v2.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_commands_v2.py`:

```python
import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock
from bot.config.loader import load_config


# ── helpers ──────────────────────────────────────────────────────────────────

MINIMAL = {
    "admins": [111],
    "masking": {"users": {}},
    "pairs": [{
        "name": "p1",
        "group_a_chat_id": -100111,
        "group_b_chat_id": -100222,
        "bidirectional": True,
        "enabled": True,
        "filters": {"types": {"allow": ["text"]}, "keywords": {"block": [], "allow": []}},
        "masking": {"a_to_b": {}, "b_to_a": {}},
    }],
}


def _cfg(tmp_path, extra=None):
    data = {**MINIMAL, **(extra or {})}
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return load_config(str(p)), str(p)


def _update(user_id: int):
    u = MagicMock()
    u.effective_user.id = user_id
    u.message.reply_text = AsyncMock()
    return u


def _ctx(*args):
    c = MagicMock()
    c.args = list(args)
    return c


# ── /set tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_recovery_window(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_set(_update(111), _ctx("recovery_window", "30"), config=config)
    assert config.recovery_window_minutes == 30


@pytest.mark.asyncio
async def test_set_recovery_window_invalid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_set(u, _ctx("recovery_window", "notanumber"), config=config)
    u.message.reply_text.assert_called_once()
    assert "Invalid" in u.message.reply_text.call_args[0][0]
    assert config.recovery_window_minutes == 15  # unchanged


@pytest.mark.asyncio
async def test_set_alert_chat(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_set(_update(111), _ctx("alert_chat", "999888777"), config=config)
    assert config.monitoring is not None
    assert config.monitoring.alert_chat_id == 999888777


@pytest.mark.asyncio
async def test_set_unknown_key_replies_usage(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_set(u, _ctx("unknown_key", "value"), config=config)
    u.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_set_unauthorized_ignored(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_set
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(999)  # not an admin
    await cmd_set(u, _ctx("recovery_window", "30"), config=config)
    u.message.reply_text.assert_not_called()
    assert config.recovery_window_minutes == 15


# ── /admin tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_add(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_admin(_update(111), _ctx("add", "222"), config=config)
    assert 222 in config.admins


@pytest.mark.asyncio
async def test_admin_add_duplicate_is_idempotent(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_admin(_update(111), _ctx("add", "111"), config=config)
    assert config.admins.count(111) == 1  # no duplicate


@pytest.mark.asyncio
async def test_admin_remove_valid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path, extra={"admins": [111, 222]})
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_admin(_update(111), _ctx("remove", "222"), config=config)
    assert 222 not in config.admins


@pytest.mark.asyncio
async def test_admin_remove_last_admin_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path)  # only admin is 111
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_admin(u, _ctx("remove", "111"), config=config)
    assert 111 in config.admins
    u.message.reply_text.assert_called_once()
    assert "last admin" in u.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_admin_remove_self_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_admin
    config, path = _cfg(tmp_path, extra={"admins": [111, 222]})
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_admin(u, _ctx("remove", "111"), config=config)
    assert 111 in config.admins
    u.message.reply_text.assert_called_once()
    assert "yourself" in u.message.reply_text.call_args[0][0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands_v2.py::test_set_recovery_window \
       tests/test_commands_v2.py::test_admin_add -v
```

Expected: FAIL with `ImportError: cannot import name 'cmd_set'`

- [ ] **Step 3: Add `cmd_set` and `cmd_admin` to `bot/handlers/commands.py`**

Append to the bottom of `bot/handlers/commands.py` (keep all existing code intact):

```python
async def cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /set recovery_window <minutes>
      /set alert_chat <chat_id>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage:\n/set recovery_window <minutes>\n/set alert_chat <chat_id>")
        return

    key, value = args[0], args[1]

    if key == "recovery_window":
        try:
            minutes = int(value)
        except ValueError:
            await update.message.reply_text("Invalid value. Usage: /set recovery_window <minutes>")
            return
        config._raw["recovery_window_minutes"] = minutes
        save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Recovery window set to {minutes} minutes.")

    elif key == "alert_chat":
        try:
            chat_id = int(value)
        except ValueError:
            await update.message.reply_text("Invalid value. Usage: /set alert_chat <chat_id>")
            return
        config._raw.setdefault("monitoring", {})["alert_chat_id"] = chat_id
        save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Alert chat set to {chat_id}.")

    else:
        await update.message.reply_text("Unknown key. Available: recovery_window, alert_chat")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /admin add <user_id>
      /admin remove <user_id>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if not args or args[0] not in ("add", "remove"):
        await update.message.reply_text("Usage:\n/admin add <user_id>\n/admin remove <user_id>")
        return

    action = args[0]
    if len(args) < 2:
        await update.message.reply_text(f"Usage: /admin {action} <user_id>")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    if action == "add":
        if user_id not in config._raw.get("admins", []):
            config._raw.setdefault("admins", []).append(user_id)
            save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Admin {user_id} added.")

    elif action == "remove":
        caller_id = update.effective_user.id
        if user_id == caller_id:
            await update.message.reply_text("Cannot remove yourself.")
            return
        if len(config.admins) <= 1:
            await update.message.reply_text("Cannot remove the last admin.")
            return
        if user_id in config._raw.get("admins", []):
            config._raw["admins"].remove(user_id)
            save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Admin {user_id} removed.")
```

- [ ] **Step 4: Run /set and /admin tests**

```bash
pytest tests/test_commands_v2.py -k "set or admin" -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/commands.py tests/test_commands_v2.py
git commit -m "feat: add /set and /admin runtime commands"
```

---

## Task 7: /pair commands

**Files:**
- Modify: `bot/handlers/commands.py`
- Modify: `tests/test_commands_v2.py`

- [ ] **Step 1: Append the failing tests to `tests/test_commands_v2.py`**

```python
# ── /pair tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pair_add_valid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_pair(_update(111), _ctx("add", "new-pair", "-100333", "-100444"), config=config)
    names = [p.name for p in config.pairs]
    assert "new-pair" in names


@pytest.mark.asyncio
async def test_pair_add_bidirectional_false(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_pair(_update(111), _ctx("add", "one-way", "-100333", "-100444", "false"), config=config)
    pair = next(p for p in config.pairs if p.name == "one-way")
    assert pair.bidirectional is False


@pytest.mark.asyncio
async def test_pair_add_duplicate_name_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_pair(u, _ctx("add", "p1", "-100333", "-100444"), config=config)
    u.message.reply_text.assert_called_once()
    assert "already exists" in u.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_pair_add_invalid_chat_id_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_pair(u, _ctx("add", "new-pair", "notanid", "-100444"), config=config)
    u.message.reply_text.assert_called_once()
    assert "Invalid chat ID" in u.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_pair_remove_valid(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    await cmd_pair(_update(111), _ctx("remove", "p1"), config=config)
    names = [p.name for p in config.pairs]
    assert "p1" not in names


@pytest.mark.asyncio
async def test_pair_remove_unknown_blocked(tmp_path, monkeypatch):
    from bot.handlers.commands import cmd_pair
    config, path = _cfg(tmp_path)
    monkeypatch.setattr("bot.handlers.commands.CONFIG_PATH", path)
    u = _update(111)
    await cmd_pair(u, _ctx("remove", "ghost"), config=config)
    u.message.reply_text.assert_called_once()
    assert "not found" in u.message.reply_text.call_args[0][0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands_v2.py -k "pair" -v
```

Expected: FAIL with `ImportError: cannot import name 'cmd_pair'`

- [ ] **Step 3: Add `cmd_pair` to `bot/handlers/commands.py`**

Append to the bottom of `bot/handlers/commands.py`:

```python
_DEFAULT_PAIR_TYPES = ["text", "photo", "video", "sticker", "document", "voice", "animation"]


async def cmd_pair(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /pair add <name> <group_a_id> <group_b_id> [true|false]
      /pair remove <name>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if not args or args[0] not in ("add", "remove"):
        await update.message.reply_text(
            "Usage:\n"
            "/pair add <name> <group_a_id> <group_b_id> [true|false]\n"
            "/pair remove <name>"
        )
        return

    action = args[0]

    if action == "add":
        if len(args) < 4:
            await update.message.reply_text(
                "Usage: /pair add <name> <group_a_id> <group_b_id> [true|false]"
            )
            return
        name = args[1]
        try:
            group_a_id = int(args[2])
            group_b_id = int(args[3])
        except ValueError:
            await update.message.reply_text("Invalid chat ID.")
            return
        bidirectional = True
        if len(args) >= 5:
            bidirectional = args[4].lower() != "false"
        if any(p.name == name for p in config.pairs):
            await update.message.reply_text(f"Pair '{name}' already exists.")
            return
        new_pair = {
            "name": name,
            "group_a_chat_id": group_a_id,
            "group_b_chat_id": group_b_id,
            "bidirectional": bidirectional,
            "enabled": True,
            "filters": {
                "types": {"allow": _DEFAULT_PAIR_TYPES},
                "keywords": {"block": [], "allow": []},
            },
            "masking": {"a_to_b": {}, "b_to_a": {}},
        }
        config._raw.setdefault("pairs", []).append(new_pair)
        save_and_reload(config, CONFIG_PATH)
        bidir_str = "bidirectional" if bidirectional else "one-way"
        await update.message.reply_text(f"Pair '{name}' added ({bidir_str}).")

    elif action == "remove":
        if len(args) < 2:
            await update.message.reply_text("Usage: /pair remove <name>")
            return
        name = args[1]
        if not any(p.name == name for p in config.pairs):
            await update.message.reply_text(f"Pair '{name}' not found.")
            return
        config._raw["pairs"] = [p for p in config._raw.get("pairs", []) if p["name"] != name]
        save_and_reload(config, CONFIG_PATH)
        await update.message.reply_text(f"Pair '{name}' removed.")
```

- [ ] **Step 4: Run /pair tests**

```bash
pytest tests/test_commands_v2.py -k "pair" -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/commands.py tests/test_commands_v2.py
git commit -m "feat: add /pair add and /pair remove commands"
```

---

## Task 8: /stats command

**Files:**
- Modify: `bot/handlers/commands.py`
- Modify: `tests/test_commands_v2.py`

- [ ] **Step 1: Append the failing tests to `tests/test_commands_v2.py`**

```python
# ── /stats tests ──────────────────────────────────────────────────────────────

from bot.stats.counter import StatsCounter


@pytest.mark.asyncio
async def test_stats_all_pairs(tmp_path):
    from bot.handlers.commands import cmd_stats
    config, _ = _cfg(tmp_path)
    stats = StatsCounter(str(tmp_path / "stats.json"))
    stats.increment("p1")
    stats.increment("p1")
    u = _update(111)
    await cmd_stats(u, _ctx(), config=config, stats=stats)
    u.message.reply_text.assert_called_once()
    reply = u.message.reply_text.call_args[0][0]
    assert "p1" in reply
    assert "2 today" in reply


@pytest.mark.asyncio
async def test_stats_single_pair(tmp_path):
    from bot.handlers.commands import cmd_stats
    config, _ = _cfg(tmp_path)
    stats = StatsCounter(str(tmp_path / "stats.json"))
    stats.increment("p1")
    u = _update(111)
    await cmd_stats(u, _ctx("p1"), config=config, stats=stats)
    reply = u.message.reply_text.call_args[0][0]
    assert "p1" in reply
    assert "1 today" in reply


@pytest.mark.asyncio
async def test_stats_unknown_pair(tmp_path):
    from bot.handlers.commands import cmd_stats
    config, _ = _cfg(tmp_path)
    stats = StatsCounter(str(tmp_path / "stats.json"))
    u = _update(111)
    await cmd_stats(u, _ctx("ghost"), config=config, stats=stats)
    reply = u.message.reply_text.call_args[0][0]
    assert "not found" in reply
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands_v2.py -k "stats" -v
```

Expected: FAIL with `ImportError: cannot import name 'cmd_stats'`

- [ ] **Step 3: Add `cmd_stats` to `bot/handlers/commands.py`**

First, add this import at the top of `bot/handlers/commands.py` alongside the existing imports:

```python
from bot.stats.counter import StatsCounter
```

Then append to the bottom of `bot/handlers/commands.py`:

```python
async def cmd_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config: Config,
    stats: StatsCounter,
) -> None:
    """
    Usage:
      /stats
      /stats <pair-name>
    """
    if not _is_admin(update.effective_user.id, config):
        return

    if context.args:
        pair_name = context.args[0]
        if not any(p.name == pair_name for p in config.pairs):
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        counts = stats.query(pair_name)
        text = f"*Stats*\n\n{pair_name}: {counts['today']} today, {counts['week']} this week"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        lines = ["*Stats*\n"]
        for pair in config.pairs:
            counts = stats.query(pair.name)
            lines.append(f"{pair.name}: {counts['today']} today, {counts['week']} this week")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
```

- [ ] **Step 4: Run /stats tests**

```bash
pytest tests/test_commands_v2.py -k "stats" -v
```

Expected: All PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/commands.py tests/test_commands_v2.py
git commit -m "feat: add /stats command"
```

---

## Task 9: Auto group ID discovery

**Files:**
- Create: `bot/handlers/membership.py`
- Create: `tests/test_membership.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_membership.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.handlers.membership import handle_bot_added
from bot.config.loader import Config, GlobalMaskingConfig, PairConfig, FilterConfig, PairMaskingConfig


def _make_config(admin_id: int = 111) -> Config:
    return Config(
        admins=[admin_id],
        masking=GlobalMaskingConfig(users={}),
        pairs=[],
        _raw={},
    )


def _make_update(status: str = "member", chat_type: str = "supergroup",
                 chat_id: int = -1009999999, chat_title: str = "Test Group"):
    new_member = MagicMock()
    new_member.status = status

    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type
    chat.title = chat_title

    chat_member_updated = MagicMock()
    chat_member_updated.new_chat_member = new_member
    chat_member_updated.chat = chat

    update = MagicMock()
    update.my_chat_member = chat_member_updated
    return update


@pytest.mark.asyncio
async def test_bot_added_sends_dm_to_first_admin():
    config = _make_config(admin_id=111)
    update = _make_update(status="member", chat_id=-1009999999, chat_title="Support Group")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_called_once()
    call_kwargs = context.bot.send_message.call_args
    assert call_kwargs[1]["chat_id"] == 111 or call_kwargs[0][0] == 111
    text = call_kwargs[1].get("text", "") or call_kwargs[0][1]
    assert "-1009999999" in text
    assert "Support Group" in text
    assert "/pair add" in text


@pytest.mark.asyncio
async def test_bot_added_ignored_for_non_group():
    config = _make_config()
    update = _make_update(status="member", chat_type="private")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_bot_added_ignored_when_removed():
    config = _make_config()
    update = _make_update(status="left")
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_bot_added(update, context, config=config)

    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_bot_added_dm_failure_does_not_crash():
    config = _make_config()
    update = _make_update(status="member")
    context = MagicMock()
    context.bot.send_message = AsyncMock(side_effect=Exception("Forbidden"))

    # Should not raise
    await handle_bot_added(update, context, config=config)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_membership.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.membership'`

- [ ] **Step 3: Create `bot/handlers/membership.py`**

```python
from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import Config

logger = logging.getLogger(__name__)


async def handle_bot_added(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config: Config,
) -> None:
    chat_member = update.my_chat_member
    if not chat_member:
        return

    new_status = chat_member.new_chat_member.status
    if new_status not in ("member", "administrator"):
        return

    chat = chat_member.chat
    if chat.type not in ("group", "supergroup"):
        return

    if not config.admins:
        return

    chat_id = chat.id
    chat_name = chat.title or "Unknown"
    text = (
        f"Bot added to group:\n"
        f"Name: {chat_name}\n"
        f"Chat ID: {chat_id}\n\n"
        f"Use: /pair add <name> {chat_id} <other_group_id>"
    )

    try:
        await context.bot.send_message(chat_id=config.admins[0], text=text)
    except Exception as e:
        logger.warning("Could not DM admin on group join: %s", e)
```

- [ ] **Step 4: Run membership tests**

```bash
pytest tests/test_membership.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/membership.py tests/test_membership.py
git commit -m "feat: add auto group ID discovery on bot membership event"
```

---

## Task 10: Main.py wiring

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace `main.py` with the updated version**

```python
from __future__ import annotations
import asyncio
import logging
import os
from functools import partial
from dotenv import load_dotenv
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
        asyncio.create_task(run_health_server(port=health_port))
        if config.monitoring and config.monitoring.alert_chat_id:
            try:
                await app.bot.send_message(
                    chat_id=config.monitoring.alert_chat_id, text="Bot started"
                )
            except Exception as e:
                logger.warning("Could not send startup alert: %s", e)

    async def post_shutdown(app: Application) -> None:
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
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: wire rate limiter, health server, monitoring alerts, and all v2 handlers"
```

---

## Task 11: Config files, requirements, and deployment docs

**Files:**
- Modify: `config.yaml`
- Modify: `.env.example`
- Modify: `requirements.txt`
- Modify: `deploy/DEPLOY.md`

- [ ] **Step 1: Update `config.yaml`**

```yaml
admins:
  - 123456789  # Replace with your Telegram user ID

recovery_window_minutes: 15   # 0 = replay all buffered messages; >0 = skip older than N min

monitoring:                    # Remove this block entirely to disable startup/shutdown alerts
  alert_chat_id: 123456789     # Chat ID to receive alerts (use your user ID for DMs)

masking:
  users: {}

pairs:
  - name: "customer-internal"
    group_a_chat_id: -1001234567890
    group_b_chat_id: -1009876543210
    bidirectional: true
    enabled: true
    filters:
      types:
        allow: [text, photo, video, sticker, document, voice, animation]
      keywords:
        block: []
        allow: []
    masking:
      a_to_b: {}
      b_to_a: {}
```

- [ ] **Step 2: Update `.env.example`**

```
BOT_TOKEN=your_bot_token_here
HEALTH_PORT=8080
```

- [ ] **Step 3: Update `requirements.txt`**

```
python-telegram-bot==21.6
PyYAML==6.0.2
python-dotenv==1.0.1
aiohttp==3.11.11
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 4: Append v2 section to `deploy/DEPLOY.md`**

Append to the end of `deploy/DEPLOY.md`:

```markdown
---

## v2: Health Monitoring Setup

### 1. Open port 8080 on the server

```bash
ufw allow 8080/tcp
```

Or add an inbound rule via the DigitalOcean Cloud Firewall dashboard (TCP port 8080, all sources).

### 2. Verify health endpoint

After deploying and starting the service:

```bash
curl http://localhost:8080/health
# → {"status": "ok", "uptime_seconds": 42}
```

### 3. Set up UptimeRobot (free external monitor)

1. Create a free account at https://uptimerobot.com
2. Click **Add New Monitor**
3. Type: **HTTP(s)**
4. URL: `http://<your-droplet-ip>:8080/health`
5. Monitoring interval: **5 minutes**
6. Alert contacts: add your email, or configure a Telegram alert contact

UptimeRobot will alert you when the health endpoint stops responding (bot crashed or server down).

### 4. Configure Telegram alerts (optional)

In `config.yaml`, set `monitoring.alert_chat_id` to your personal Telegram user ID to receive
"Bot started" / "Bot stopping" messages directly.

To find your user ID: send any message to the bot and check the logs, or use @userinfobot.

Before setting `alert_chat_id`, send `/start` to your bot in a private chat — otherwise
the bot cannot DM you.
```

- [ ] **Step 5: Run the full test suite one final time**

```bash
pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 6: Final commit**

```bash
git add config.yaml .env.example requirements.txt deploy/DEPLOY.md
git commit -m "chore: update config, env, requirements, and deploy docs for v2"
```
