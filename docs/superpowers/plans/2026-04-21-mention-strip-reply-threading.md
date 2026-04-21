# @mention Stripping & Reply Threading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip Telegram @username mentions from forwarded text (preserving emails) and preserve reply threading between groups, including cross-group reply chains.

**Architecture:** Approach A — inline changes to existing modules plus one new file. `strip_mentions()` and updated `forward_message()` live in `relay.py`; a new `ReplyMap` JSON-backed store in `bot/reply_map.py` tracks bidirectional message ID mappings. Config flag `strip_mentions` (default `true`) parsed in `loader.py`. Both features wired through `handle_message` → `forward_message`.

**Tech Stack:** Python 3.9+, python-telegram-bot 21.6, pytest 8.3.3, pytest-asyncio 0.24.0

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `bot/config/loader.py` | Modify | Add `strip_mentions: bool = True` to `Config`; parse from yaml |
| `bot/reply_map.py` | Create | `ReplyMap` — JSON-backed bidirectional `(chat_id, msg_id)` store |
| `bot/forwarder/relay.py` | Modify | Add `strip_mentions()`, update `forward_message()` signature and logic |
| `bot/handlers/message.py` | Modify | Pass `reply_map` and `config` to `forward_message` |
| `main.py` | Modify | Instantiate `ReplyMap`, wire via `partial()` |
| `config.yaml` | Modify | Add `strip_mentions: true` |
| `tests/test_config_loader.py` | Modify | Tests for `strip_mentions` flag |
| `tests/test_reply_map.py` | Create | Tests for `ReplyMap` |
| `tests/test_mention_strip.py` | Create | Tests for `strip_mentions()` function |
| `tests/test_relay.py` | Create | Integration tests for updated `forward_message()` |
| `tests/test_message_handler.py` | Modify | Add `reply_map` arg to all `handle_message` calls |

---

## Task 1: Config — add strip_mentions flag

**Files:**
- Modify: `tests/test_config_loader.py`
- Modify: `bot/config/loader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_loader.py`:

```python
def test_strip_mentions_defaults_to_true(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG))
    config = load_config(str(config_file))
    assert config.strip_mentions is True


def test_strip_mentions_explicit_false(tmp_path):
    data = {**MINIMAL_CONFIG, "strip_mentions": False}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    config = load_config(str(config_file))
    assert config.strip_mentions is False
```

- [ ] **Step 2: Run to verify fail**

```
pytest tests/test_config_loader.py::test_strip_mentions_defaults_to_true tests/test_config_loader.py::test_strip_mentions_explicit_false -v
```

Expected: `FAILED` — `Config` has no attribute `strip_mentions`

- [ ] **Step 3: Add field to Config dataclass**

In `bot/config/loader.py`, add `strip_mentions` to the `Config` dataclass (after `recovery_window_minutes`):

```python
@dataclass
class Config:
    admins: list[int]
    masking: GlobalMaskingConfig
    pairs: list[PairConfig]
    recovery_window_minutes: int = 15
    strip_mentions: bool = True
    monitoring: MonitoringConfig | None = None
    _raw: dict = field(default_factory=dict, repr=False)
```

In `load_config()`, add parsing before `return Config(...)`:

```python
    return Config(
        admins=[int(a) for a in raw["admins"]],
        masking=global_masking,
        pairs=[_parse_pair(p) for p in raw["pairs"]],
        recovery_window_minutes=int(raw.get("recovery_window_minutes", 15)),
        strip_mentions=bool(raw.get("strip_mentions", True)),
        monitoring=monitoring,
        _raw=raw,
    )
```

- [ ] **Step 4: Run to verify pass**

```
pytest tests/test_config_loader.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add bot/config/loader.py tests/test_config_loader.py
git commit -m "feat: add strip_mentions config flag (default true)"
```

---

## Task 2: ReplyMap store

**Files:**
- Create: `bot/reply_map.py`
- Create: `tests/test_reply_map.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reply_map.py`:

```python
import pytest
from bot.reply_map import ReplyMap


def test_lookup_returns_none_when_not_found(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    assert store.lookup(-100111, 42) is None


def test_record_and_lookup_forward_direction(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    assert store.lookup(-100111, 100) == (-100222, 200)


def test_record_and_lookup_reverse_direction(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    assert store.lookup(-100222, 200) == (-100111, 100)


def test_persists_to_disk(tmp_path):
    path = str(tmp_path / "reply_map.json")
    store = ReplyMap(path)
    store.record(-100111, 100, -100222, 200)

    store2 = ReplyMap(path)
    assert store2.lookup(-100111, 100) == (-100222, 200)
    assert store2.lookup(-100222, 200) == (-100111, 100)


def test_multiple_entries_independent(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    store.record(-100111, 101, -100222, 201)
    assert store.lookup(-100111, 100) == (-100222, 200)
    assert store.lookup(-100111, 101) == (-100222, 201)


def test_overwrite_existing_entry(tmp_path):
    store = ReplyMap(str(tmp_path / "reply_map.json"))
    store.record(-100111, 100, -100222, 200)
    store.record(-100111, 100, -100222, 999)
    assert store.lookup(-100111, 100) == (-100222, 999)
```

- [ ] **Step 2: Run to verify fail**

```
pytest tests/test_reply_map.py -v
```

Expected: `ERROR` — cannot import `ReplyMap`

- [ ] **Step 3: Implement ReplyMap**

Create `bot/reply_map.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

```
pytest tests/test_reply_map.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add bot/reply_map.py tests/test_reply_map.py
git commit -m "feat: add ReplyMap — bidirectional JSON-backed message ID store"
```

---

## Task 3: strip_mentions() function

**Files:**
- Create: `tests/test_mention_strip.py`
- Modify: `bot/forwarder/relay.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mention_strip.py`:

```python
from bot.forwarder.relay import strip_mentions


def test_strips_standalone_mention():
    assert strip_mentions("Hey @nicky can you help?") == "Hey can you help?"


def test_preserves_email():
    assert strip_mentions("Send to abc@gmail.com please") == "Send to abc@gmail.com please"


def test_strips_mention_at_start():
    assert strip_mentions("@john what do you think?") == "what do you think?"


def test_strips_mention_at_end():
    assert strip_mentions("Thanks @bob") == "Thanks"


def test_strips_multiple_mentions():
    assert strip_mentions("@alice and @bob please review") == "and please review"


def test_preserves_email_with_subdomain():
    assert strip_mentions("user@domain.org sent this") == "user@domain.org sent this"


def test_empty_string():
    assert strip_mentions("") == ""


def test_only_mention_becomes_empty():
    assert strip_mentions("@nicky") == ""


def test_collapses_extra_whitespace():
    assert strip_mentions("hello @x world") == "hello world"
```

- [ ] **Step 2: Run to verify fail**

```
pytest tests/test_mention_strip.py -v
```

Expected: `ERROR` — cannot import `strip_mentions` from `bot.forwarder.relay`

- [ ] **Step 3: Add regex and function to relay.py**

At the top of `bot/forwarder/relay.py`, add `import re` and the function after the imports:

```python
from __future__ import annotations
import re
import logging
from telegram import Message
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r'(?<!\w)@\w+')


def strip_mentions(text: str) -> str:
    result = re.sub(_MENTION_RE, '', text)
    return ' '.join(result.split())
```

Leave the rest of `relay.py` unchanged for now.

- [ ] **Step 4: Run to verify pass**

```
pytest tests/test_mention_strip.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add bot/forwarder/relay.py tests/test_mention_strip.py
git commit -m "feat: add strip_mentions() — strips @username, preserves emails"
```

---

## Task 4: Wire forward_message with reply threading and mention stripping

**Files:**
- Create: `tests/test_relay.py`
- Modify: `bot/forwarder/relay.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_relay.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.forwarder.relay import forward_message
from bot.reply_map import ReplyMap
from bot.config.loader import Config, GlobalMaskingConfig, PairMaskingConfig, PairConfig, FilterConfig


def _make_config(strip_mentions: bool = True) -> Config:
    return Config(
        admins=[1],
        masking=GlobalMaskingConfig(users={}),
        pairs=[],
        strip_mentions=strip_mentions,
        _raw={},
    )


def _make_message(
    text: str = "hello world",
    reply_to_id: int = None,
    chat_id: int = -100111,
    msg_id: int = 42,
):
    msg = MagicMock()
    msg.chat.id = chat_id
    msg.message_id = msg_id
    msg.text = text
    msg.caption = None
    msg.photo = None
    msg.video = None
    msg.document = None
    msg.voice = None
    msg.sticker = None
    msg.animation = None
    msg.reply_to_message = None
    if reply_to_id is not None:
        msg.reply_to_message = MagicMock()
        msg.reply_to_message.message_id = reply_to_id
    return msg


def _make_context(sent_msg_id: int = 99):
    context = MagicMock()
    sent = MagicMock()
    sent.message_id = sent_msg_id
    context.bot.send_message = AsyncMock(return_value=sent)
    context.bot.send_photo = AsyncMock(return_value=sent)
    context.bot.send_video = AsyncMock(return_value=sent)
    context.bot.send_document = AsyncMock(return_value=sent)
    context.bot.send_voice = AsyncMock(return_value=sent)
    context.bot.send_sticker = AsyncMock(return_value=sent)
    context.bot.send_animation = AsyncMock(return_value=sent)
    return context


@pytest.mark.asyncio
async def test_strip_mentions_applied_when_enabled(tmp_path):
    config = _make_config(strip_mentions=True)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    msg = _make_message(text="Hey @nicky check this")
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert "@nicky" not in sent_text
    assert "check this" in sent_text


@pytest.mark.asyncio
async def test_strip_mentions_skipped_when_disabled(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    msg = _make_message(text="Hey @nicky check this")
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert "@nicky" in sent_text


@pytest.mark.asyncio
async def test_reply_to_id_set_when_lookup_succeeds(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    reply_map.record(-100111, 50, -100222, 77)

    msg = _make_message(text="hello", reply_to_id=50)
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] == 77


@pytest.mark.asyncio
async def test_reply_to_id_is_none_when_lookup_misses(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))

    msg = _make_message(text="hello", reply_to_id=999)
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] is None


@pytest.mark.asyncio
async def test_reply_to_id_is_none_when_no_reply(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))

    msg = _make_message(text="hello")
    context = _make_context()

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] is None


@pytest.mark.asyncio
async def test_sent_message_recorded_in_reply_map(tmp_path):
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))

    msg = _make_message(text="hello", chat_id=-100111, msg_id=42)
    context = _make_context(sent_msg_id=88)

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    assert reply_map.lookup(-100111, 42) == (-100222, 88)
    assert reply_map.lookup(-100222, 88) == (-100111, 42)


@pytest.mark.asyncio
async def test_cross_group_reply_chain(tmp_path):
    """Message from B forwarded to A; user in A replies; reply shows in B."""
    config = _make_config(strip_mentions=False)
    reply_map = ReplyMap(str(tmp_path / "reply_map.json"))
    # B sent msg 10 → forwarded to A as msg 20
    reply_map.record(-100222, 10, -100111, 20)

    # User in A replies to msg 20 (the forwarded B message)
    msg = _make_message(text="got it", chat_id=-100111, msg_id=21, reply_to_id=20)
    context = _make_context(sent_msg_id=11)

    await forward_message(msg, "Alice", -100222, context, reply_map, config)

    # reply_to_message_id should be 10 (original message in B)
    assert context.bot.send_message.call_args.kwargs["reply_to_message_id"] == 10
```

- [ ] **Step 2: Run to verify fail**

```
pytest tests/test_relay.py -v
```

Expected: `FAILED` — `forward_message()` takes 4 positional arguments but 6 were given

- [ ] **Step 3: Rewrite forward_message in relay.py**

Replace the entire content of `bot/forwarder/relay.py` with:

```python
from __future__ import annotations
import re
import logging
from telegram import Message
from telegram.error import RetryAfter
from telegram.ext import ContextTypes
from bot.reply_map import ReplyMap
from bot.config.loader import Config

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r'(?<!\w)@\w+')


def strip_mentions(text: str) -> str:
    result = re.sub(_MENTION_RE, '', text)
    return ' '.join(result.split())


async def forward_message(
    message: Message,
    display_name: str,
    dest_chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_map: ReplyMap,
    config: Config,
) -> None:
    src_chat_id = message.chat.id
    src_msg_id = message.message_id

    reply_to_id: int | None = None
    if message.reply_to_message:
        result = reply_map.lookup(src_chat_id, message.reply_to_message.message_id)
        if result is not None:
            _, reply_to_id = result

    def clean(text: str | None) -> str | None:
        if text is None:
            return None
        return strip_mentions(text) if config.strip_mentions else text

    sent = None
    try:
        if message.text:
            sent = await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name}: {clean(message.text)}",
                reply_to_message_id=reply_to_id,
            )

        elif message.photo:
            caption = f"{display_name}: {clean(message.caption)}" if message.caption else None
            header = None if caption else f"[photo sent by {display_name}]"
            if header:
                await context.bot.send_message(
                    chat_id=dest_chat_id,
                    text=header,
                    reply_to_message_id=reply_to_id,
                )
            sent = await context.bot.send_photo(
                chat_id=dest_chat_id,
                photo=message.photo[-1].file_id,
                caption=caption,
                reply_to_message_id=reply_to_id if caption else None,
            )

        elif message.video:
            caption = f"{display_name}: {clean(message.caption)}" if message.caption else None
            header = None if caption else f"[video sent by {display_name}]"
            if header:
                await context.bot.send_message(
                    chat_id=dest_chat_id,
                    text=header,
                    reply_to_message_id=reply_to_id,
                )
            sent = await context.bot.send_video(
                chat_id=dest_chat_id,
                video=message.video.file_id,
                caption=caption,
                reply_to_message_id=reply_to_id if caption else None,
            )

        elif message.document:
            caption = f"{display_name}: {clean(message.caption)}" if message.caption else None
            header = None if caption else f"[file sent by {display_name}]"
            if header:
                await context.bot.send_message(
                    chat_id=dest_chat_id,
                    text=header,
                    reply_to_message_id=reply_to_id,
                )
            sent = await context.bot.send_document(
                chat_id=dest_chat_id,
                document=message.document.file_id,
                caption=caption,
                reply_to_message_id=reply_to_id if caption else None,
            )

        elif message.voice:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a voice message:",
                reply_to_message_id=reply_to_id,
            )
            sent = await context.bot.send_voice(
                chat_id=dest_chat_id,
                voice=message.voice.file_id,
            )

        elif message.sticker:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a sticker:",
                reply_to_message_id=reply_to_id,
            )
            sent = await context.bot.send_sticker(
                chat_id=dest_chat_id,
                sticker=message.sticker.file_id,
            )

        elif message.animation:
            await context.bot.send_message(
                chat_id=dest_chat_id,
                text=f"{display_name} sent a GIF:",
                reply_to_message_id=reply_to_id,
            )
            sent = await context.bot.send_animation(
                chat_id=dest_chat_id,
                animation=message.animation.file_id,
            )

    except RetryAfter:
        raise
    except Exception as e:
        logger.error(
            "Failed to forward message to %s from %s: %s",
            dest_chat_id,
            display_name,
            e,
        )

    if sent is not None:
        try:
            reply_map.record(src_chat_id, src_msg_id, dest_chat_id, sent.message_id)
        except Exception as e:
            logger.warning("Failed to record reply map entry: %s", e)
```

- [ ] **Step 4: Run to verify pass**

```
pytest tests/test_relay.py tests/test_mention_strip.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add bot/forwarder/relay.py tests/test_relay.py
git commit -m "feat: wire reply threading and mention stripping into forward_message"
```

---

## Task 5: Wire handle_message and main.py

**Files:**
- Modify: `bot/handlers/message.py`
- Modify: `main.py`
- Modify: `config.yaml`
- Modify: `tests/test_message_handler.py`

- [ ] **Step 1: Update test_message_handler.py to pass reply_map**

In `tests/test_message_handler.py`, add `from bot.reply_map import ReplyMap` to imports, then add `reply_map=MagicMock()` to every `handle_message(...)` call. There are 5 such calls (lines 66, 81, 94, 107, 123). Also add one new test:

Full updated `tests/test_message_handler.py`:

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
    context.bot.id = 1

    return update, context


@pytest.mark.asyncio
async def test_age_filter_skips_stale_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=20 * 60)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_not_called()
    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_age_filter_passes_recent_message():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=5 * 60)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_called_once()
    stats.increment.assert_called_once_with("test-pair")


@pytest.mark.asyncio
async def test_age_filter_disabled_when_zero():
    config = _make_config(recovery_window_minutes=0)
    update, context = _make_update_and_context(age_seconds=60 * 60)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_called_once()


@pytest.mark.asyncio
async def test_stats_not_incremented_when_message_dropped_by_filter():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context()
    config.pairs[0].enabled = False
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock):
        await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_stats_not_incremented_when_relay_raises():
    config = _make_config(recovery_window_minutes=15)
    update, context = _make_update_and_context(age_seconds=0)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock, side_effect=Exception("relay failed")):
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            with pytest.raises(Exception, match="relay failed"):
                await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    stats.increment.assert_not_called()


@pytest.mark.asyncio
async def test_reply_map_and_config_passed_to_forward_message():
    config = _make_config(recovery_window_minutes=0)
    update, context = _make_update_and_context(age_seconds=0)
    store = MagicMock()
    stats = MagicMock()
    reply_map = MagicMock()

    with patch("bot.handlers.message.forward_message", new_callable=AsyncMock) as mock_fwd:
        with patch("bot.handlers.message.resolve_display_name", return_value="Tester"):
            await handle_message(update, context, config=config, store=store, stats=stats, reply_map=reply_map)

    mock_fwd.assert_called_once()
    call_args = mock_fwd.call_args.args
    assert call_args[4] is reply_map
    assert call_args[5] is config
```

- [ ] **Step 2: Run to verify fail**

```
pytest tests/test_message_handler.py -v
```

Expected: `FAILED` — `handle_message() got an unexpected keyword argument 'reply_map'`

- [ ] **Step 3: Update handle_message signature and forward_message call**

Replace `bot/handlers/message.py` with:

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
from bot.reply_map import ReplyMap
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
    reply_map: ReplyMap,
) -> None:
    message = update.effective_message
    if not message or not message.from_user:
        return

    if message.from_user.id == context.bot.id:
        return

    if config.recovery_window_minutes > 0:
        msg_date = message.date
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - msg_date).total_seconds()
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
    await forward_message(message, display_name, dest_chat_id, context, reply_map, config)
    stats.increment(pair.name)
```

- [ ] **Step 4: Run message handler tests**

```
pytest tests/test_message_handler.py -v
```

Expected: all pass

- [ ] **Step 5: Update main.py to instantiate ReplyMap and wire it**

In `main.py`, add the import and instantiation:

```python
from bot.reply_map import ReplyMap
```

Add after `stats = StatsCounter("data/stats.json")`:

```python
    reply_map = ReplyMap("data/reply_map.json")
```

Update the `handle_message` partial:

```python
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            partial(handle_message, config=config, store=store, stats=stats, reply_map=reply_map),
        )
    )
```

- [ ] **Step 6: Update config.yaml**

Add `strip_mentions: true` after `recovery_window_minutes`:

```yaml
admins:
  - 2043771174

recovery_window_minutes: 15
strip_mentions: true

monitoring:
  alert_chat_id: 2043771174

masking:
  users: {}

pairs:
  - name: "customer-internal"
    group_a_chat_id: -1003746947950
    group_b_chat_id: -1003766457201
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

- [ ] **Step 7: Run full test suite**

```
pytest -v
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/handlers/message.py main.py config.yaml tests/test_message_handler.py
git commit -m "feat: wire reply_map into handle_message and main; add strip_mentions to config"
```
