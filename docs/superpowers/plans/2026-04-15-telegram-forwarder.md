# Telegram Message Forwarder Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that monitors group pairs and forwards messages bidirectionally with configurable filters and sender masking.

**Architecture:** Single Python async process using `python-telegram-bot` v20+ in polling mode. Messages pass through a pipeline: loop-detection → pair routing → type filter → keyword filter → masking → relay. Config lives in `config.yaml` (persisted) and `data/masks.json` (auto-generated). Admin commands mutate both files at runtime.

**Tech Stack:** Python 3.11+, `python-telegram-bot` v20+, `PyYAML`, `python-dotenv`, `pytest`, `systemd`

---

## File Map

| File | Responsibility |
|---|---|
| `main.py` | Entry point — load config, build Application, register handlers, start polling |
| `bot/__init__.py` | Empty package marker |
| `bot/config/__init__.py` | Empty package marker |
| `bot/config/loader.py` | Load + validate `config.yaml` into `Config` dataclass; expose `load_config()` |
| `bot/config/writer.py` | Persist runtime mutations back to `config.yaml`; expose `save_config()` |
| `bot/filters/__init__.py` | Empty package marker |
| `bot/filters/type_filter.py` | `passes_type_filter(message, pair, direction) -> bool` |
| `bot/filters/keyword_filter.py` | `passes_keyword_filter(text, pair, direction) -> bool` |
| `bot/masking/__init__.py` | Empty package marker |
| `bot/masking/engine.py` | `resolve_display_name(user_id, first_name, pair, direction, config) -> str`; manage `masks.json` |
| `bot/forwarder/__init__.py` | Empty package marker |
| `bot/forwarder/relay.py` | `forward_message(message, display_name, dest_chat_id, context) -> None` |
| `bot/handlers/__init__.py` | Empty package marker |
| `bot/handlers/message.py` | `handle_message(update, context)` — routes messages through the full pipeline |
| `bot/handlers/commands.py` | Admin command handlers: `/status`, `/enable`, `/disable`, `/filter`, `/mask`, `/unmask` |
| `tests/test_type_filter.py` | Unit tests for type filter |
| `tests/test_keyword_filter.py` | Unit tests for keyword filter |
| `tests/test_masking.py` | Unit tests for masking engine |
| `tests/test_config_loader.py` | Unit tests for config loading and validation |
| `config.yaml` | Starter config with one sample pair |
| `.env.example` | Template showing required env vars |
| `requirements.txt` | Pinned dependencies |
| `deploy/telegram-forwarder.service` | systemd unit file |

---

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.yaml`
- Create: `bot/__init__.py`
- Create: `bot/config/__init__.py`
- Create: `bot/filters/__init__.py`
- Create: `bot/masking/__init__.py`
- Create: `bot/forwarder/__init__.py`
- Create: `bot/handlers/__init__.py`
- Create: `tests/__init__.py`
- Create: `data/.gitkeep`

- [ ] **Step 1: Create `requirements.txt`**

```
python-telegram-bot==21.6
PyYAML==6.0.2
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Create `.env.example`**

```
BOT_TOKEN=your_bot_token_here
```

- [ ] **Step 3: Create `config.yaml`**

```yaml
admins:
  - 123456789  # Replace with your Telegram user ID

masking:
  users: {}    # Global masking defaults: user_id -> {alias: "Name"} or {alias: null}

pairs:
  - name: "example-pair"
    group_a_chat_id: -1001111111111
    group_b_chat_id: -1002222222222
    bidirectional: true
    enabled: true
    filters:
      types:
        allow:
          - text
          - photo
          - video
          - sticker
          - document
          - voice
          - animation
      keywords:
        block: []
        allow: []
    masking:
      a_to_b: {}
      b_to_a: {}
```

- [ ] **Step 4: Create all empty `__init__.py` files and `data/.gitkeep`**

```bash
touch bot/__init__.py
touch bot/config/__init__.py
touch bot/filters/__init__.py
touch bot/masking/__init__.py
touch bot/forwarder/__init__.py
touch bot/handlers/__init__.py
touch tests/__init__.py
mkdir -p data && touch data/.gitkeep
```

- [ ] **Step 5: Create virtual environment and install deps**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: All packages install without error.

- [ ] **Step 6: Commit**

```bash
git init
git add requirements.txt .env.example config.yaml bot/ tests/ data/.gitkeep
git commit -m "feat: scaffold project structure and dependencies"
```

---

### Task 2: Config loader

**Files:**
- Create: `bot/config/loader.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_loader.py`:

```python
import pytest
import yaml
import os
from bot.config.loader import load_config, Config, PairConfig, FilterConfig, GlobalMaskingConfig


MINIMAL_CONFIG = {
    "admins": [123456789],
    "masking": {"users": {}},
    "pairs": [
        {
            "name": "test-pair",
            "group_a_chat_id": -1001111111111,
            "group_b_chat_id": -1002222222222,
            "bidirectional": True,
            "enabled": True,
            "filters": {
                "types": {"allow": ["text", "photo"]},
                "keywords": {"block": [], "allow": []},
            },
            "masking": {"a_to_b": {}, "b_to_a": {}},
        }
    ],
}


def test_load_config_returns_config_object(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    assert isinstance(config, Config)


def test_load_config_admins(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    assert config.admins == [123456789]


def test_load_config_pair_fields(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    pair = config.pairs[0]
    assert pair.name == "test-pair"
    assert pair.group_a_chat_id == -1001111111111
    assert pair.group_b_chat_id == -1002222222222
    assert pair.bidirectional is True
    assert pair.enabled is True


def test_load_config_pair_defaults_bidirectional_true(tmp_path):
    data = {**MINIMAL_CONFIG}
    data["pairs"][0] = {**data["pairs"][0]}
    del data["pairs"][0]["bidirectional"]
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    assert config.pairs[0].bidirectional is True


def test_load_config_missing_pairs_raises(tmp_path):
    data = {"admins": [1], "masking": {"users": {}}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="pairs"):
        load_config(str(config_file))


def test_load_config_missing_admins_raises(tmp_path):
    data = {**MINIMAL_CONFIG}
    del data["admins"]
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    with pytest.raises(ValueError, match="admins"):
        load_config(str(config_file))


def test_load_config_global_masking_users(tmp_path):
    data = {**MINIMAL_CONFIG}
    data["masking"] = {"users": {111: {"alias": "Alpha"}, 222: {"alias": None}}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    assert config.masking.users[111]["alias"] == "Alpha"
    assert config.masking.users[222]["alias"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate
pytest tests/test_config_loader.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.config.loader'`

- [ ] **Step 3: Implement `bot/config/loader.py`**

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
    a_to_b: dict[int, dict]  # user_id -> {"alias": str | None}
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
    users: dict[int, dict]  # user_id -> {"alias": str | None}


@dataclass
class Config:
    admins: list[int]
    masking: GlobalMaskingConfig
    pairs: list[PairConfig]
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

    return Config(
        admins=[int(a) for a in raw["admins"]],
        masking=global_masking,
        pairs=[_parse_pair(p) for p in raw["pairs"]],
        _raw=raw,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config_loader.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/config/loader.py tests/test_config_loader.py
git commit -m "feat: config loader with validation and dataclasses"
```

---

### Task 3: Config writer

**Files:**
- Create: `bot/config/writer.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_loader.py`:

```python
from bot.config.writer import save_config, save_and_reload


def test_save_config_persists_changes(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    config._raw["admins"].append(999999999)
    save_config(config, str(config_file))
    reloaded = load_config(str(config_file))
    assert 999999999 in reloaded.admins


def test_save_and_reload_updates_in_place(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    config._raw["admins"].append(777777777)
    save_and_reload(config, str(config_file))
    assert 777777777 in config.admins
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config_loader.py::test_save_config_persists_changes -v
```

Expected: `ModuleNotFoundError: No module named 'bot.config.writer'`

- [ ] **Step 3: Implement `bot/config/writer.py`**

```python
from __future__ import annotations
import yaml
from bot.config.loader import Config, load_config


def save_config(config: Config, path: str = "config.yaml") -> None:
    with open(path, "w") as f:
        yaml.dump(config._raw, f, default_flow_style=False, allow_unicode=True)


def save_and_reload(config: Config, path: str = "config.yaml") -> None:
    """Persist _raw to disk, then re-parse it and update config in-place.

    This ensures that runtime command changes (filter, mask) take effect
    immediately without requiring a bot restart.
    """
    save_config(config, path)
    fresh = load_config(path)
    config.admins = fresh.admins
    config.masking = fresh.masking
    config.pairs = fresh.pairs
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config_loader.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/config/writer.py tests/test_config_loader.py
git commit -m "feat: config writer persists runtime changes to config.yaml"
```

---

### Task 4: Type filter

**Files:**
- Create: `bot/filters/type_filter.py`
- Create: `tests/test_type_filter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_type_filter.py`:

```python
import pytest
from unittest.mock import MagicMock
from bot.filters.type_filter import passes_type_filter, detect_message_type
from bot.config.loader import PairConfig, FilterConfig, PairMaskingConfig


def _make_pair(allowed_types: list[str]) -> PairConfig:
    return PairConfig(
        name="p",
        group_a_chat_id=-1,
        group_b_chat_id=-2,
        bidirectional=True,
        enabled=True,
        filters=FilterConfig(
            types_allow=allowed_types,
            keywords_block=[],
            keywords_allow=[],
        ),
        masking=PairMaskingConfig(a_to_b={}, b_to_a={}),
    )


def _make_message(**kwargs) -> MagicMock:
    msg = MagicMock()
    msg.text = kwargs.get("text", None)
    msg.photo = kwargs.get("photo", None)
    msg.video = kwargs.get("video", None)
    msg.sticker = kwargs.get("sticker", None)
    msg.document = kwargs.get("document", None)
    msg.voice = kwargs.get("voice", None)
    msg.animation = kwargs.get("animation", None)
    return msg


def test_text_message_allowed():
    pair = _make_pair(["text"])
    msg = _make_message(text="hello")
    assert passes_type_filter(msg, pair) is True


def test_text_message_blocked_when_not_in_allow():
    pair = _make_pair(["photo"])
    msg = _make_message(text="hello")
    assert passes_type_filter(msg, pair) is False


def test_photo_message_allowed():
    pair = _make_pair(["photo"])
    msg = _make_message(photo=[MagicMock()])
    assert passes_type_filter(msg, pair) is True


def test_sticker_message_allowed():
    pair = _make_pair(["sticker"])
    msg = _make_message(sticker=MagicMock())
    assert passes_type_filter(msg, pair) is True


def test_unknown_message_type_blocked():
    pair = _make_pair(["text", "photo"])
    msg = _make_message()  # no known fields set
    assert passes_type_filter(msg, pair) is False


def test_detect_message_type_text():
    msg = _make_message(text="hi")
    assert detect_message_type(msg) == "text"


def test_detect_message_type_photo():
    msg = _make_message(photo=[MagicMock()])
    assert detect_message_type(msg) == "photo"


def test_detect_message_type_unknown():
    msg = _make_message()
    assert detect_message_type(msg) == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_type_filter.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.filters.type_filter'`

- [ ] **Step 3: Implement `bot/filters/type_filter.py`**

```python
from __future__ import annotations
from telegram import Message
from bot.config.loader import PairConfig

_TYPE_CHECKS = [
    ("text",      lambda m: bool(m.text)),
    ("photo",     lambda m: bool(m.photo)),
    ("video",     lambda m: bool(m.video)),
    ("sticker",   lambda m: bool(m.sticker)),
    ("document",  lambda m: bool(m.document)),
    ("voice",     lambda m: bool(m.voice)),
    ("animation", lambda m: bool(m.animation)),
]


def detect_message_type(message: Message) -> str:
    for type_name, check in _TYPE_CHECKS:
        if check(message):
            return type_name
    return "unknown"


def passes_type_filter(message: Message, pair: PairConfig) -> bool:
    msg_type = detect_message_type(message)
    return msg_type in pair.filters.types_allow
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_type_filter.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/filters/type_filter.py tests/test_type_filter.py
git commit -m "feat: type filter — detect and allow/block message types"
```

---

### Task 5: Keyword filter

**Files:**
- Create: `bot/filters/keyword_filter.py`
- Create: `tests/test_keyword_filter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_keyword_filter.py`:

```python
import pytest
from bot.filters.keyword_filter import passes_keyword_filter
from bot.config.loader import PairConfig, FilterConfig, PairMaskingConfig


def _make_pair(block: list[str], allow: list[str]) -> PairConfig:
    return PairConfig(
        name="p",
        group_a_chat_id=-1,
        group_b_chat_id=-2,
        bidirectional=True,
        enabled=True,
        filters=FilterConfig(
            types_allow=["text"],
            keywords_block=block,
            keywords_allow=allow,
        ),
        masking=PairMaskingConfig(a_to_b={}, b_to_a={}),
    )


def test_no_filters_passes():
    pair = _make_pair(block=[], allow=[])
    assert passes_keyword_filter("any message", pair) is True


def test_blocklist_blocks_matching_message():
    pair = _make_pair(block=["spam"], allow=[])
    assert passes_keyword_filter("this is spam here", pair) is False


def test_blocklist_passes_non_matching():
    pair = _make_pair(block=["spam"], allow=[])
    assert passes_keyword_filter("hello everyone", pair) is True


def test_allowlist_passes_matching():
    pair = _make_pair(block=[], allow=["urgent"])
    assert passes_keyword_filter("this is urgent", pair) is True


def test_allowlist_blocks_non_matching():
    pair = _make_pair(block=[], allow=["urgent"])
    assert passes_keyword_filter("hello everyone", pair) is False


def test_blocklist_takes_priority_over_allowlist():
    pair = _make_pair(block=["spam"], allow=["spam"])
    assert passes_keyword_filter("spam", pair) is False


def test_none_text_passes_with_no_allowlist():
    pair = _make_pair(block=[], allow=[])
    assert passes_keyword_filter(None, pair) is True


def test_none_text_blocked_when_allowlist_set():
    pair = _make_pair(block=[], allow=["urgent"])
    assert passes_keyword_filter(None, pair) is False


def test_keyword_match_is_case_insensitive():
    pair = _make_pair(block=["SPAM"], allow=[])
    assert passes_keyword_filter("this is spam", pair) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_keyword_filter.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.filters.keyword_filter'`

- [ ] **Step 3: Implement `bot/filters/keyword_filter.py`**

```python
from __future__ import annotations
from bot.config.loader import PairConfig


def passes_keyword_filter(text: str | None, pair: PairConfig) -> bool:
    block = pair.filters.keywords_block
    allow = pair.filters.keywords_allow
    lowered = text.lower() if text else ""

    if block and any(kw.lower() in lowered for kw in block):
        return False

    if allow:
        if not text:
            return False
        return any(kw.lower() in lowered for kw in allow)

    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_keyword_filter.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/filters/keyword_filter.py tests/test_keyword_filter.py
git commit -m "feat: keyword filter with block/allow lists, case-insensitive"
```

---

### Task 6: Masking engine

**Files:**
- Create: `bot/masking/engine.py`
- Create: `tests/test_masking.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_masking.py`:

```python
import pytest
import json
import os
from bot.masking.engine import resolve_display_name, MaskStore
from bot.config.loader import Config, GlobalMaskingConfig, PairConfig, FilterConfig, PairMaskingConfig


def _make_config(global_users: dict, pair_a_to_b: dict = None, pair_b_to_a: dict = None) -> Config:
    return Config(
        admins=[1],
        masking=GlobalMaskingConfig(users={int(k): v for k, v in global_users.items()}),
        pairs=[
            PairConfig(
                name="test-pair",
                group_a_chat_id=-1,
                group_b_chat_id=-2,
                bidirectional=True,
                enabled=True,
                filters=FilterConfig(types_allow=["text"], keywords_block=[], keywords_allow=[]),
                masking=PairMaskingConfig(
                    a_to_b={int(k): v for k, v in (pair_a_to_b or {}).items()},
                    b_to_a={int(k): v for k, v in (pair_b_to_a or {}).items()},
                ),
            )
        ],
        _raw={},
    )


def test_no_masking_returns_real_name(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={})
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert result == "John"


def test_global_fixed_alias(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={111: {"alias": "Customer Alpha"}})
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert result == "Customer Alpha"


def test_global_anon_id_assigned_consistently(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={111: {"alias": None}})
    pair = config.pairs[0]
    first = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    second = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert first == second
    assert first.startswith("User #")


def test_global_anon_different_users_different_numbers(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(global_users={111: {"alias": None}, 222: {"alias": None}})
    pair = config.pairs[0]
    r1 = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    r2 = resolve_display_name(222, "Jane", pair, "a_to_b", config, store)
    assert r1 != r2


def test_pair_override_takes_priority_over_global(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(
        global_users={111: {"alias": "Global Name"}},
        pair_a_to_b={111: {"alias": "VIP Override"}},
    )
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store)
    assert result == "VIP Override"


def test_pair_direction_a_to_b_not_applied_for_b_to_a(tmp_path):
    store = MaskStore(str(tmp_path / "masks.json"))
    config = _make_config(
        global_users={},
        pair_a_to_b={111: {"alias": "A-side name"}},
    )
    pair = config.pairs[0]
    result = resolve_display_name(111, "John", pair, "b_to_a", config, store)
    assert result == "John"


def test_mask_store_persists_to_disk(tmp_path):
    mask_path = str(tmp_path / "masks.json")
    store = MaskStore(mask_path)
    config = _make_config(global_users={111: {"alias": None}})
    pair = config.pairs[0]
    resolve_display_name(111, "John", pair, "a_to_b", config, store)

    store2 = MaskStore(mask_path)
    result = resolve_display_name(111, "John", pair, "a_to_b", config, store2)
    assert result.startswith("User #")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_masking.py -v
```

Expected: `ModuleNotFoundError: No module named 'bot.masking.engine'`

- [ ] **Step 3: Implement `bot/masking/engine.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_masking.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/masking/engine.py tests/test_masking.py
git commit -m "feat: masking engine — fixed alias, anonymous ID, per-pair directional overrides"
```

---

### Task 7: Relay (message forwarder)

**Files:**
- Create: `bot/forwarder/relay.py`

- [ ] **Step 1: Implement `bot/forwarder/relay.py`**

No unit test here — relay calls the Telegram API and is covered by integration smoke test in Task 10.

```python
from __future__ import annotations
import logging
from telegram import Message
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


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

    except Exception as e:
        logger.error(
            "Failed to forward message to %s from %s: %s",
            dest_chat_id,
            display_name,
            e,
        )
```

- [ ] **Step 2: Commit**

```bash
git add bot/forwarder/relay.py
git commit -m "feat: relay — format and forward all v1 message types to destination"
```

---

### Task 8: Message handler (pipeline)

**Files:**
- Create: `bot/handlers/message.py`

- [ ] **Step 1: Implement `bot/handlers/message.py`**

```python
from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import Config, PairConfig
from bot.filters.type_filter import passes_type_filter
from bot.filters.keyword_filter import passes_keyword_filter
from bot.masking.engine import resolve_display_name, MaskStore
from bot.forwarder.relay import forward_message

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
) -> None:
    message = update.effective_message
    if not message or not message.from_user:
        return

    # Loop prevention: drop messages sent by the bot itself
    if message.from_user.id == context.bot.id:
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
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers/message.py
git commit -m "feat: message handler — full pipeline with loop prevention and routing"
```

---

### Task 9: Admin commands

**Files:**
- Create: `bot/handlers/commands.py`

- [ ] **Step 1: Implement `bot/handlers/commands.py`**

```python
from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.config.loader import Config
from bot.config.writer import save_and_reload

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


def _is_admin(user_id: int, config: Config) -> bool:
    return user_id in config.admins


def _find_pair_raw(config: Config, pair_name: str) -> dict | None:
    for p in config._raw.get("pairs", []):
        if p["name"] == pair_name:
            return p
    return None


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    if not _is_admin(update.effective_user.id, config):
        return
    lines = ["*Forwarding Pairs Status*"]
    for pair in config.pairs:
        state = "enabled" if pair.enabled else "disabled"
        direction = "bidirectional" if pair.bidirectional else "one-way (A→B)"
        lines.append(
            f"\n*{pair.name}* — {state}, {direction}\n"
            f"  A: `{pair.group_a_chat_id}`\n"
            f"  B: `{pair.group_b_chat_id}`\n"
            f"  Types: {', '.join(pair.filters.types_allow)}\n"
            f"  Block keywords: {pair.filters.keywords_block or 'none'}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_enable(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    if not _is_admin(update.effective_user.id, config):
        return
    if not context.args:
        await update.message.reply_text("Usage: /enable <pair-name>")
        return
    pair_name = context.args[0]
    raw = _find_pair_raw(config, pair_name)
    if not raw:
        await update.message.reply_text(f"Pair '{pair_name}' not found.")
        return
    raw["enabled"] = True
    for pair in config.pairs:
        if pair.name == pair_name:
            pair.enabled = True
    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Pair '{pair_name}' enabled.")


async def cmd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    if not _is_admin(update.effective_user.id, config):
        return
    if not context.args:
        await update.message.reply_text("Usage: /disable <pair-name>")
        return
    pair_name = context.args[0]
    raw = _find_pair_raw(config, pair_name)
    if not raw:
        await update.message.reply_text(f"Pair '{pair_name}' not found.")
        return
    raw["enabled"] = False
    for pair in config.pairs:
        if pair.name == pair_name:
            pair.enabled = False
    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Pair '{pair_name}' disabled.")


async def cmd_filter(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage:
      /filter <pair> block type <type>
      /filter <pair> allow type <type>
      /filter <pair> block keyword <word>
      /filter <pair> allow keyword <word>
      /filter <pair> remove keyword <word>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: /filter <pair> <block|allow|remove> <type|keyword> <value>"
        )
        return

    pair_name, action, category, value = args[0], args[1], args[2], args[3]
    raw = _find_pair_raw(config, pair_name)
    if not raw:
        await update.message.reply_text(f"Pair '{pair_name}' not found.")
        return

    filters = raw.setdefault("filters", {})
    if category == "type":
        types_allow = filters.setdefault("types", {}).setdefault("allow", [])
        if action == "allow" and value not in types_allow:
            types_allow.append(value)
        elif action == "block" and value in types_allow:
            types_allow.remove(value)
        elif action == "remove" and value in types_allow:
            types_allow.remove(value)
    elif category == "keyword":
        keywords = filters.setdefault("keywords", {})
        block_list = keywords.setdefault("block", [])
        allow_list = keywords.setdefault("allow", [])
        if action == "block" and value not in block_list:
            block_list.append(value)
        elif action == "allow" and value not in allow_list:
            allow_list.append(value)
        elif action == "remove":
            if value in block_list:
                block_list.remove(value)
            if value in allow_list:
                allow_list.remove(value)
    else:
        await update.message.reply_text("Category must be 'type' or 'keyword'.")
        return

    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Filter updated for '{pair_name}'.")


async def cmd_mask(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage: /mask <pair> <a_to_b|b_to_a|global> <user_id> <alias|anon>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: /mask <pair> <a_to_b|b_to_a|global> <user_id> <alias|anon>"
        )
        return

    pair_name, direction, user_id_str, alias = args[0], args[1], args[2], " ".join(args[3:])
    try:
        user_id = int(user_id_str)
    except ValueError:
        await update.message.reply_text("user_id must be a number.")
        return

    alias_value = None if alias.lower() == "anon" else alias

    if direction == "global":
        config._raw.setdefault("masking", {}).setdefault("users", {})[user_id] = {
            "alias": alias_value
        }
    else:
        raw = _find_pair_raw(config, pair_name)
        if not raw:
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        raw.setdefault("masking", {}).setdefault(direction, {})[user_id] = {
            "alias": alias_value
        }

    save_and_reload(config, CONFIG_PATH)
    label = "anonymous" if alias_value is None else f'"{alias_value}"'
    await update.message.reply_text(f"User {user_id} will now appear as {label}.")


async def cmd_unmask(update: Update, context: ContextTypes.DEFAULT_TYPE, config: Config) -> None:
    """
    Usage: /unmask <pair> <a_to_b|b_to_a|global> <user_id>
    """
    if not _is_admin(update.effective_user.id, config):
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /unmask <pair> <a_to_b|b_to_a|global> <user_id>"
        )
        return

    pair_name, direction, user_id_str = args[0], args[1], args[2]
    try:
        user_id = int(user_id_str)
    except ValueError:
        await update.message.reply_text("user_id must be a number.")
        return

    if direction == "global":
        users = config._raw.get("masking", {}).get("users", {})
        users.pop(user_id, None)
    else:
        raw = _find_pair_raw(config, pair_name)
        if not raw:
            await update.message.reply_text(f"Pair '{pair_name}' not found.")
            return
        raw.get("masking", {}).get(direction, {}).pop(user_id, None)

    save_and_reload(config, CONFIG_PATH)
    await update.message.reply_text(f"Masking removed for user {user_id}.")
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers/commands.py
git commit -m "feat: admin commands — status, enable, disable, filter, mask, unmask"
```

---

### Task 10: Entry point and wiring

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement `main.py`**

```python
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
```

- [ ] **Step 2: Run all tests to verify nothing broken**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: entry point — wire all handlers and start polling"
```

---

### Task 11: Smoke test with real bot

Before deploying, verify the bot works end-to-end with real Telegram groups.

**Prerequisites:**
- Create a bot via [@BotFather](https://t.me/BotFather) and get the token
- Create two test Telegram groups
- Add the bot as admin to both groups
- Get the chat IDs (send a message to the group, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find `chat.id`)

- [ ] **Step 1: Configure `.env` with real token**

```bash
cp .env.example .env
# Edit .env: BOT_TOKEN=your_real_bot_token
```

- [ ] **Step 2: Update `config.yaml` with real group IDs**

Replace `group_a_chat_id` and `group_b_chat_id` with your real test group chat IDs. Replace the `admins` list with your own Telegram user ID.

- [ ] **Step 3: Run the bot locally**

```bash
source venv/bin/activate
python main.py
```

Expected: `Bot started. Polling...` with no errors.

- [ ] **Step 4: Send a test message in Group A**

Send "Hello from Group A" in your Group A. Verify it appears in Group B as:
```
YourName: Hello from Group A
```

- [ ] **Step 5: Verify bidirectional**

Reply in Group B with "Reply from Group B". Verify it appears in Group A as:
```
YourName: Reply from Group B
```

- [ ] **Step 6: Test loop prevention**

The bot's forwarded message in Group B should NOT trigger another forward back to Group A. Confirm no duplicate messages appear.

- [ ] **Step 7: Test an admin command**

In any group or private chat with the bot, send:
```
/status
```

Verify the bot replies with the pair status summary.

---

### Task 12: systemd deployment on DigitalOcean

**Files:**
- Create: `deploy/telegram-forwarder.service`

- [ ] **Step 1: Create `deploy/telegram-forwarder.service`**

```ini
[Unit]
Description=Telegram Message Forwarder Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/telegram-forwarder
EnvironmentFile=/opt/telegram-forwarder/.env
ExecStart=/opt/telegram-forwarder/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit the service file**

```bash
git add deploy/telegram-forwarder.service
git commit -m "feat: systemd service unit for DigitalOcean deployment"
```

- [ ] **Step 3: Deploy to droplet**

SSH into your DigitalOcean droplet, then:

```bash
# Install Python 3.11+ if not present
sudo apt update && sudo apt install -y python3.11 python3.11-venv git

# Clone the repo
sudo git clone <your-repo-url> /opt/telegram-forwarder
cd /opt/telegram-forwarder

# Set up virtualenv and install deps
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and fill in secrets
sudo cp .env.example .env
sudo nano .env   # set BOT_TOKEN

# Copy systemd unit
sudo cp deploy/telegram-forwarder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-forwarder
sudo systemctl start telegram-forwarder
```

- [ ] **Step 4: Verify service is running**

```bash
sudo systemctl status telegram-forwarder
```

Expected: `Active: active (running)`

- [ ] **Step 5: Tail live logs**

```bash
journalctl -u telegram-forwarder -f
```

Send a test message in Group A and verify the log shows the message being processed and forwarded.
