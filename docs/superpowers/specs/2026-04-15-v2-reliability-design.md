# Telegram Forwarder Bot v2 — Reliability & Monitoring Design Spec

**Date:** 2026-04-15
**Status:** Approved

---

## Overview

Four targeted improvements to the existing v1 bot:

1. **Rate limiting** — buffer outgoing relay messages to stay within Telegram's flood limits; nothing is dropped during bursts.
2. **Health endpoint** — HTTP `GET /health` so external uptime monitors (e.g. UptimeRobot) can detect when the bot is down.
3. **Monitoring alerts** — Telegram messages sent to an admin chat on startup and graceful shutdown; crash detection delegated to the external monitor.
4. **Message recovery** — replay Telegram-buffered messages on restart, skipping anything older than a configurable age window (default 15 min).

Webhook mode and additional forwarding features (edit propagation, reply threading, etc.) are explicitly out of scope for v2. Polling remains the transport.

---

## Scope

**Included:**
- `AIORateLimiter` wired into the PTB Application builder
- `aiohttp`-based health server running as a background asyncio task
- Startup and graceful-shutdown Telegram alerts via `Application.post_init` / `post_shutdown`
- Message age filter in `handle_message` — stale buffered messages are silently skipped
- New `monitoring` config block in `config.yaml`
- `HEALTH_PORT` env var (default `8080`)
- Updated deployment guide covering firewall rule and UptimeRobot setup

**Excluded:**
- Webhook mode
- Edit/delete propagation
- Reply threading
- Web dashboard
- Any forwarding feature not in v1

---

## Architecture

No structural change to the bot's core pipeline. All changes are additive or single-line modifications to existing files.

```
main.py
  ├── AIORateLimiter on Application builder
  ├── post_init hook
  │     ├── asyncio.create_task(run_health_server())
  │     └── bot.send_message(alert_chat_id, "Bot started")
  └── post_shutdown hook
        └── bot.send_message(alert_chat_id, "Bot stopping")

bot/health/server.py  (new)
  └── GET /health → {"status": "ok", "uptime_seconds": N}

bot/handlers/message.py
  └── age check at top of handle_message — return if message older than recovery_window_minutes

config.yaml
  ├── recovery_window_minutes: 15
  └── monitoring:
        alert_chat_id: <int>

.env / .env.example
  └── HEALTH_PORT=8080
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

## Files Changed

| File | Change |
|---|---|
| `main.py` | Add `AIORateLimiter`; add `post_init`/`post_shutdown` hooks; remove `drop_pending_updates=True` |
| `bot/config/loader.py` | Add `MonitoringConfig` dataclass; add `recovery_window_minutes` field to `Config` |
| `bot/handlers/message.py` | Add age filter at top of `handle_message` |
| `bot/health/__init__.py` | New — empty package marker |
| `bot/health/server.py` | New — aiohttp health server |
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

---

## Testing

- **Rate limiter:** Verify `AIORateLimiter` is attached by checking the Application object in a unit test; integration test by sending a burst of messages and confirming all arrive without `RetryAfter` errors.
- **Health server:** `GET http://localhost:8080/health` returns 200 and valid JSON in an integration test.
- **Age filter:** Unit test with a message whose `date` is set to `now - 20min` — should be skipped when `recovery_window_minutes=15`. Message at `now - 10min` should pass.
- **Monitoring alerts:** Mock `bot.send_message` and verify it is called with the correct chat ID and text in `post_init` and `post_shutdown`.
