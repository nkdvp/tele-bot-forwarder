# Design: @mention Stripping & Reply Threading

**Date:** 2026-04-21
**Branch:** v2-reliability

## Overview

Two features added to the Telegram forwarder bot:

1. **@mention stripping** — strip Telegram `@username` mentions from forwarded text while preserving email addresses like `abc@gmail.com`.
2. **Reply threading** — forwarded messages preserve reply structure in the destination group, including cross-group reply chains.

---

## Feature 1: @mention Stripping

### Configuration

One new top-level flag in `config.yaml`, default `true`:

```yaml
strip_mentions: true
```

`Config` dataclass gains `strip_mentions: bool = True`, parsed via `raw.get("strip_mentions", True)` in `loader.py`.

### Implementation

A module-level regex and helper function added to `relay.py`:

```python
import re
_MENTION_RE = re.compile(r'(?<!\w)@\w+')

def strip_mentions(text: str) -> str:
    result = re.sub(_MENTION_RE, '', text)
    return ' '.join(result.split())
```

**Regex rationale:** `(?<!\w)@\w+` matches `@` not preceded by a word character. This matches `@nicky` (standalone mention) but not `abc@gmail.com` (the `c` before `@` is a word character).

Applied in `forward_message()` to both `message.text` and `message.caption` when `config.strip_mentions` is `True`, before the text is sent.

---

## Feature 2: Reply Threading

### Data Store

New file `bot/reply_map.py` — a JSON-backed bidirectional message ID store, following the same pattern as `MaskStore`.

```python
class ReplyMap:
    def __init__(self, path: str = "data/reply_map.json"): ...

    def record(self, src_chat: int, src_msg: int, dst_chat: int, dst_msg: int) -> None:
        # Stores both directions so lookup works from either side

    def lookup(self, chat_id: int, msg_id: int) -> tuple[int, int] | None:
        # Returns (other_chat_id, other_msg_id) or None
```

Storage format (`data/reply_map.json`):

```json
{
  "-1001234:501": [-1009999, 88],
  "-1009999:88":  [-1001234, 501]
}
```

Both directions are written on every forward, enabling bidirectional reply chain lookup (cross-group replies included).

No pruning strategy — at typical forwarding bot volume the file stays small (10,000 entries ≈ 1 MB).

### Wiring in `relay.py`

`forward_message()` gains two new parameters:

```python
async def forward_message(
    message: Message,
    display_name: str,
    dest_chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_map: ReplyMap,
    config: Config,
) -> None:
```

Per-send logic order:

1. **Reply lookup** — if `message.reply_to_message` exists, call `reply_map.lookup(src_chat_id, reply_to_msg_id)` to get the counterpart message ID in the destination group.
2. **Mention stripping** — if `config.strip_mentions`, apply `strip_mentions()` to text/caption.
3. **Send** — pass `reply_to_message_id` to every `send_message` / `send_photo` / `send_video` / `send_document` / `send_voice` / `send_sticker` / `send_animation` call. python-telegram-bot supports this parameter on all send methods.
4. **Record** — after successful send, call `reply_map.record(src_chat, src_msg_id, dest_chat, sent_msg.message_id)`.

**Fallback:** if the lookup returns `None` (message predates the feature, or map entry missing), the bot sends without `reply_to_message_id` — no error, graceful degradation.

### Wiring in `message.py`

`handle_message` already has `config` in scope. A `ReplyMap` instance is constructed at startup (alongside `MaskStore` and `StatsCounter`) and passed through to `forward_message`.

---

## Data Flow

```
incoming message (with optional reply_to)
        │
        ▼
handle_message (message.py)
        │  passes: message, display_name, dest_chat_id, reply_map, config
        ▼
forward_message (relay.py)
    1. reply_map.lookup(src_chat, reply_to_msg_id)  → reply_to_message_id or None
    2. strip_mentions(text/caption)                 → cleaned text
    3. bot.send_*(reply_to_message_id=...)          → sent_msg
    4. reply_map.record(src, src_msg, dst, sent_msg.message_id)
```

---

## Error Handling

- Reply lookup miss → send without reply marker (no exception)
- `strip_mentions` on empty/None text → guarded by existing None checks in relay.py
- `reply_map.record` failure → log and continue (reply map is best-effort)

---

## Files Changed

| File | Change |
|------|--------|
| `config.yaml` | Add `strip_mentions: true` |
| `bot/config/loader.py` | Add `strip_mentions: bool = True` to `Config`, parse in `load_config` |
| `bot/reply_map.py` | New — `ReplyMap` store |
| `bot/forwarder/relay.py` | Add `strip_mentions()`, update `forward_message()` signature and logic |
| `bot/handlers/message.py` | Pass `reply_map` and `config` to `forward_message` |
| `main.py` | Instantiate `ReplyMap` at startup |
