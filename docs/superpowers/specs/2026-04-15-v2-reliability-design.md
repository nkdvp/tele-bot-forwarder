# Telegram Forwarder Bot v2 — Reliability & Monitoring Design Spec

**Date:** 2026-04-15
**Status:** Approved

---

## Overview

Ten targeted improvements to the existing v1 bot:

1. **Rate limiting** — buffer outgoing relay messages to stay within Telegram's flood limits; nothing is dropped during bursts.
2. **Health endpoint** — HTTP `GET /health` so external uptime monitors (e.g. UptimeRobot) can detect when the bot is down.
3. **Monitoring alerts** — Telegram messages sent to an admin chat (including direct DMs) on startup and graceful shutdown; crash detection delegated to the external monitor.
4. **Message recovery** — replay Telegram-buffered messages on restart, skipping anything older than a configurable age window (default 15 min).
5. **Runtime config commands** — `/set` commands to change `recovery_window_minutes` and `alert_chat_id` without restart.
6. **Runtime admin management** — `/admin add` and `/admin remove` commands with lockout protection.
7. **Pair management commands** — `/pair add` and `/pair remove` to manage forwarding pairs at runtime without editing `config.yaml`.
8. **Auto group ID discovery** — when the bot is added to a new group, it DMs the admin with the group name and chat ID, making pair setup frictionless.
9. **Message stats** — `/stats [pair-name]` shows forwarded message counts per pair for today and this week.
10. **Config writer patch** — `save_and_reload` extended to sync all new top-level config fields so runtime mutations stay consistent.

Webhook mode, edit/delete propagation, and reply threading are explicitly out of scope for v2. Polling remains the transport.

---

## Scope

**Included:**
- `AIORateLimiter` wired into the PTB Application builder
- `aiohttp`-based health server running as a background asyncio task
- Startup and graceful-shutdown Telegram alerts via `Application.post_init` / `post_shutdown` (supports personal DM as `alert_chat_id`)
- Message age filter in `handle_message` — stale buffered messages are silently skipped
- New `monitoring` config block in `config.yaml`
- `HEALTH_PORT` env var (default `8080`)
- `/set recovery_window <minutes>` and `/set alert_chat <chat_id>` runtime commands
- `/admin add <user_id>` and `/admin remove <user_id>` runtime commands with lockout protection
- `/pair add <name> <group_a_id> <group_b_id> [bidirectional=true]` and `/pair remove <name>` runtime commands
- Auto group ID discovery via `ChatMemberUpdated` handler — DMs the first admin when bot is added to a group
- `/stats [pair-name]` — forwarded message counts (today / this week) backed by `data/stats.json`
- `save_and_reload` patched to sync all new top-level `Config` fields
- Updated deployment guide covering firewall rule and UptimeRobot setup

**Excluded:**
- Webhook mode
- Edit/delete propagation
- Reply threading
- Web dashboard
- Any forwarding feature not in v1

---

## Architecture

No structural change to the bot's core pipeline. All changes are additive or targeted modifications to existing files.

```
main.py
  ├── AIORateLimiter on Application builder
  ├── post_init hook
  │     ├── asyncio.create_task(run_health_server())
  │     └── bot.send_message(alert_chat_id, "Bot started")
  ├── post_shutdown hook
  │     └── bot.send_message(alert_chat_id, "Bot stopping")
  └── register new handlers: /set, /admin, /pair, /stats, ChatMemberUpdated

bot/health/server.py  (new)
  └── GET /health → {"status": "ok", "uptime_seconds": N}

bot/stats/counter.py  (new)
  └── increment(pair_name) / query(pair_name) → backed by data/stats.json

bot/handlers/message.py
  └── age check at top of handle_message
  └── increment stats counter on successful relay

bot/handlers/membership.py  (new)
  └── handle_bot_added(update, context) — DM first admin with group name + chat ID

bot/config/writer.py
  └── save_and_reload patched to sync recovery_window_minutes and monitoring

config.yaml
  ├── recovery_window_minutes: 15
  └── monitoring:
        alert_chat_id: <int>

.env / .env.example
  └── HEALTH_PORT=8080

data/stats.json  (auto-created)
  └── { "pair-name": {"today": N, "week": N, "date": "YYYY-MM-DD"} }
```

---

## Components

### 1. Rate Limiter

**File:** `main.py`

```python
from telegram.ext import AIORateLimiter

app = (
    Application.builder()
    .token(token)
    .rate_limiter(AIORateLimiter())
    .build()
)
```

PTB's `AIORateLimiter` enforces:
- ~30 requests/sec globally
- ~20 messages/min per destination chat

On a `RetryAfter` flood-control response it sleeps for the required duration and retries automatically. No messages are dropped or lost during bursts.

---

### 2. Health Server

**File:** `bot/health/server.py` (new)

```
GET /health
→ 200 {"status": "ok", "uptime_seconds": <int>}
```

- Runs as a background `asyncio.Task` started in `post_init`
- Binds to `0.0.0.0:<HEALTH_PORT>` (default `8080`)
- Port is read from the `HEALTH_PORT` environment variable; falls back to `8080`
- If the bot process crashes, the health server dies with it — the endpoint goes dark, triggering the external monitor

**Dependency:** `aiohttp` added to `requirements.txt`.

---

### 3. Monitoring Alerts

**Config addition (`config.yaml`):**
```yaml
monitoring:
  alert_chat_id: 123456789   # Telegram chat ID to receive bot status messages
```

`alert_chat_id` is required when `monitoring` is present. If the key is missing or null, startup/shutdown alerts are skipped (no error).

**Behavior:**

| Event | Message sent |
|---|---|
| Successful startup | `"Bot started"` |
| Graceful shutdown (SIGTERM / restart) | `"Bot stopping"` |
| Crash / kill -9 | No Telegram message — external monitor detects via health endpoint going dark |

**Implementation:** PTB `Application` lifecycle hooks:
```python
async def _on_startup(app):
    asyncio.create_task(run_health_server(port=health_port))
    if config.monitoring and config.monitoring.alert_chat_id:
        await app.bot.send_message(config.monitoring.alert_chat_id, "Bot started")

async def _on_shutdown(app):
    if config.monitoring and config.monitoring.alert_chat_id:
        await app.bot.send_message(config.monitoring.alert_chat_id, "Bot stopping")

application.post_init = _on_startup
application.post_shutdown = _on_shutdown
```

---

### 4. Message Recovery

**Config addition (`config.yaml`):**
```yaml
recovery_window_minutes: 15
```

- `0` — process all buffered messages regardless of age (full replay)
- `>0` — skip messages older than N minutes (default: 15)

**`main.py` change:** remove `drop_pending_updates=True` from `run_polling()`.

**`bot/handlers/message.py` change:** age check inserted before the existing pipeline:

```python
from datetime import datetime, timezone

# Age filter — skip stale messages buffered during downtime
if config.recovery_window_minutes > 0:
    age = (datetime.now(timezone.utc) - message.date).total_seconds()
    if age > config.recovery_window_minutes * 60:
        logger.info("Skipping stale message %.0fs old (limit %dm)", age, config.recovery_window_minutes)
        return
```

Messages within the window are forwarded normally. On a short outage (<15 min) all missed messages are replayed. On a longer outage, only the most recent 15 minutes are replayed.

---

### 5. Config Writer Patch

**File:** `bot/config/writer.py`

`save_and_reload` currently syncs only `admins`, `masking`, and `pairs` after re-parsing. Two new lines added to sync the v2 top-level fields:

```python
config.recovery_window_minutes = fresh.recovery_window_minutes
config.monitoring = fresh.monitoring
```

This ensures `/set` and other runtime mutations to these fields are reflected in the live `Config` object without restart.

---

### 6. Auto Group ID Discovery

**File:** `bot/handlers/membership.py` (new)

When the bot is added to any group or supergroup, it sends a DM to the first admin in `config.admins` with the group's name and numeric chat ID:

```
Bot added to group:
Name: Customer Support Alpha
Chat ID: -1001234567890

Use: /pair add <name> -1001234567890 <other_group_id>
```

**Implementation:** `ChatMemberUpdated` handler filtered to `MY_CHAT_MEMBER` updates where `new_chat_member.status` is `member` or `administrator`.

The message includes a ready-to-use `/pair add` snippet so the admin can copy-paste directly.

---

### 7. Pair Management Commands

**File:** `bot/handlers/commands.py`

#### `/pair add <name> <group_a_id> <group_b_id> [true|false]`

Creates a new forwarding pair with sensible defaults:

```yaml
name: <name>
group_a_chat_id: <group_a_id>
group_b_chat_id: <group_b_id>
bidirectional: true   # default; pass "false" to override
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

Appends the raw dict to `config._raw["pairs"]`, calls `save_and_reload()`. The re-parse syncs `config.pairs` automatically.

Guards:
- Reject if `<name>` already exists among `config.pairs`
- Reject if either chat ID is not a valid integer

#### `/pair remove <name>`

Removes the pair from `config._raw["pairs"]` by name and calls `save_and_reload()`.

Guards:
- Reply `"Pair '<name>' not found."` if name does not match any pair

---

### 8. Message Stats

**File:** `bot/stats/counter.py` (new)

Backed by `data/stats.json`. Structure:

```json
{
  "customer-internal": {
    "date": "2026-04-16",
    "today": 42,
    "week": 317
  }
}
```

- `increment(pair_name)` — called in `handle_message` after a successful relay. If `date` has rolled over to a new day, resets `today` to 0. Increments both `today` and `week`. Resets `week` to 0 when a new ISO week starts.
- File is auto-created on first write if missing.
- Writes are synchronous (stats.json is tiny; no async needed).

**`/stats [pair-name]` command** (in `bot/handlers/commands.py`):

- Without argument: shows all pairs.
- With `pair-name`: shows that pair only.

Example output:
```
*Stats*

customer-internal: 42 today, 317 this week
support-escalations: 8 today, 61 this week
```

---

## Configuration

### Updated `config.yaml`

```yaml
admins:
  - 123456789

recovery_window_minutes: 15   # NEW — 0 = replay all, >0 = skip older than N min

monitoring:                    # NEW — omit entire block to disable alerts
  alert_chat_id: 123456789

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

### Updated `.env.example`

```env
BOT_TOKEN=your_bot_token_here
HEALTH_PORT=8080
```

---

## Runtime Commands (new in v2)

All commands are restricted to user IDs in `config.admins`. Unauthorised users receive no response (same as existing commands).

### `/set` — change runtime config values

| Command | Effect |
|---|---|
| `/set recovery_window <minutes>` | Update `recovery_window_minutes`. `0` = replay all. |
| `/set alert_chat <chat_id>` | Update `monitoring.alert_chat_id`. Use your personal user ID for DMs. |

Both changes persist to `config.yaml` immediately and take effect without restart. Bot replies with a confirmation message.

### `/admin` — manage the admin list

| Command | Effect |
|---|---|
| `/admin add <user_id>` | Add `user_id` to the admins list. Takes effect immediately. |
| `/admin remove <user_id>` | Remove `user_id` from the admins list. Guarded (see below). |

**Guards on `/admin remove`:**

- **Last admin protection** — refuses if removing this user would leave the admins list empty. Replies: `"Cannot remove the last admin."`
- **Self-remove protection** — refuses if `user_id` matches the caller's own ID. Replies: `"Cannot remove yourself."`

Both changes persist to `config.yaml` immediately.

### `/pair` — manage forwarding pairs

| Command | Effect |
|---|---|
| `/pair add <name> <group_a_id> <group_b_id> [true\|false]` | Add a new pair with defaults. Optional 4th arg sets `bidirectional` (default `true`). |
| `/pair remove <name>` | Remove a pair permanently. |

Both changes persist to `config.yaml` immediately and take effect without restart.

### `/stats` — message counts

| Command | Effect |
|---|---|
| `/stats` | Show forwarded message counts for all pairs (today / this week). |
| `/stats <pair-name>` | Show counts for one pair only. |

Stats are read from `data/stats.json`. Read-only command, no config change.

---

## Files Changed

| File | Change |
|---|---|
| `main.py` | Add `AIORateLimiter`; add `post_init`/`post_shutdown` hooks; remove `drop_pending_updates=True`; register `/set`, `/admin`, `/pair`, `/stats`, `ChatMemberUpdated` handlers |
| `bot/config/loader.py` | Add `MonitoringConfig` dataclass; add `recovery_window_minutes` and `monitoring` fields to `Config` |
| `bot/config/writer.py` | Patch `save_and_reload` to sync `recovery_window_minutes` and `monitoring` |
| `bot/handlers/message.py` | Add age filter; call `stats.increment` after successful relay |
| `bot/handlers/commands.py` | Add `cmd_set`, `cmd_admin`, `cmd_pair`, `cmd_stats` handlers |
| `bot/handlers/membership.py` | New — `handle_bot_added` for auto group ID discovery |
| `bot/health/__init__.py` | New — empty package marker |
| `bot/health/server.py` | New — aiohttp health server |
| `bot/stats/__init__.py` | New — empty package marker |
| `bot/stats/counter.py` | New — `increment` / `query` backed by `data/stats.json` |
| `config.yaml` | Add `recovery_window_minutes` and `monitoring` block |
| `.env.example` | Add `HEALTH_PORT=8080` |
| `requirements.txt` | Add `aiohttp` (pinned) |
| `deploy/DEPLOY.md` | Add firewall rule step and UptimeRobot setup instructions |

---

## Deployment Changes

### Firewall

Open port `8080` on the DigitalOcean droplet:

```bash
ufw allow 8080/tcp
```

Or via the DigitalOcean Cloud Firewall dashboard: add an inbound rule for TCP port 8080.

### UptimeRobot Setup

1. Create a free account at [uptimerobot.com](https://uptimerobot.com)
2. Add monitor: **HTTP(s)** type, URL `http://<your-droplet-ip>:8080/health`
3. Check interval: 5 minutes
4. Alert contact: email or Telegram (UptimeRobot supports Telegram webhook alerts natively)

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Health server port already in use | Log error at startup, continue without health server |
| `alert_chat_id` not configured | Skip startup/shutdown alerts silently |
| Alert send fails (bot banned from chat, etc.) | Log warning, do not crash |
| `RetryAfter` flood error on relay | `AIORateLimiter` sleeps and retries automatically |
| Bot restarted within recovery window | Messages in window are replayed and forwarded normally |
| Bot down longer than recovery window | Only last 15 min of buffered messages are forwarded on restart |
| `/set recovery_window` with non-integer value | Reply: `"Invalid value. Usage: /set recovery_window <minutes>"` |
| `/set alert_chat` with non-integer value | Reply: `"Invalid value. Usage: /set alert_chat <chat_id>"` |
| `/admin remove` on last admin | Reply: `"Cannot remove the last admin."` |
| `/admin remove` self-remove attempt | Reply: `"Cannot remove yourself."` |
| `/admin add` with non-integer user_id | Reply: `"Invalid user ID."` |
| `/pair add` with duplicate name | Reply: `"Pair '<name>' already exists."` |
| `/pair add` with non-integer chat ID | Reply: `"Invalid chat ID."` |
| `/pair remove` with unknown name | Reply: `"Pair '<name>' not found."` |
| `/stats` with unknown pair name | Reply: `"Pair '<name>' not found."` |
| Auto discovery — DM send fails (admin hasn't started bot) | Log warning, skip silently |
| `data/stats.json` missing | Auto-created on first `increment` call |

---

## Testing

- **Rate limiter:** Verify `AIORateLimiter` is attached by checking the Application object in a unit test; integration test by sending a burst of messages and confirming all arrive without `RetryAfter` errors.
- **Health server:** `GET http://localhost:8080/health` returns 200 and valid JSON in an integration test.
- **Age filter:** Unit test with a message whose `date` is set to `now - 20min` — should be skipped when `recovery_window_minutes=15`. Message at `now - 10min` should pass.
- **Monitoring alerts:** Mock `bot.send_message` and verify it is called with the correct chat ID and text in `post_init` and `post_shutdown`.
- **`/set` commands:** Unit test valid and invalid inputs; verify `config.yaml` is updated on disk after the command.
- **`/admin remove` guards:** Unit test last-admin case (single-element list), self-remove case, and valid removal.
- **`/admin add`:** Unit test duplicate add (idempotent — no error, no duplicate entry) and valid add.
- **`/pair add`:** Unit test duplicate name guard, invalid chat ID guard, and valid add — verify pair appears in `config.pairs` and `config._raw["pairs"]` after `save_and_reload`.
- **`/pair remove`:** Unit test unknown name and valid removal.
- **Stats counter:** Unit test `increment` day-rollover (today resets, week accumulates) and week-rollover (both reset). Unit test `query` for unknown pair returns zeros.
- **Auto group discovery:** Mock `ChatMemberUpdated` event and verify DM is sent to first admin with correct chat ID.
