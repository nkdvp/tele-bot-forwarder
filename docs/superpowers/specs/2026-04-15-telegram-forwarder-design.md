# Telegram Message Forwarder Bot — Design Spec

**Date:** 2026-04-15  
**Status:** Approved

---

## Overview

A Telegram bot that monitors one or more group pairs and forwards messages between them. Supports bidirectional forwarding, configurable message-type and keyword filters, and a sender masking system that hides real identities behind fixed aliases or anonymous IDs.

The bot runs as a Python process on a DigitalOcean droplet, managed by `systemd`. Configuration is managed via `config.yaml` (initial setup) and live Telegram admin commands (runtime changes).

---

## Scope (v1)

**Included:**
- Text, photo, video, sticker, document, voice, and animation message types
- Bidirectional forwarding between group pairs
- Per-direction message type and keyword filters
- Sender masking: fixed alias and auto-numbered anonymous ID
- Runtime admin commands via Telegram
- Persistence of runtime config changes to `config.yaml`

**Excluded (future):**
- Polls, contacts, location, live location, invoice messages (type D expansion)
- Web dashboard
- Webhook mode (polling only in v1)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Bot Process                        │
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌─────────────────┐  │
│  │ Config   │   │ Handlers │   │ Admin Commands  │  │
│  │ (yaml +  │◄──│ (inbound │   │ (/mask, /filter,│  │
│  │  runtime)│   │ messages)│   │  /status...)    │  │
│  └────┬─────┘   └────┬─────┘   └────────┬────────┘  │
│       │              │                   │           │
│       └──────────────▼───────────────────┘           │
│                      │                               │
│              ┌───────▼────────┐                      │
│              │ Filter Engine  │                      │
│              │ (type+keyword) │                      │
│              └───────┬────────┘                      │
│                      │                               │
│              ┌───────▼────────┐                      │
│              │ Masking Engine │                      │
│              │ (alias/anon ID)│                      │
│              └───────┬────────┘                      │
│                      │                               │
│              ┌───────▼────────┐                      │
│              │    Relay       │                      │
│              │ (format+send)  │                      │
│              └────────────────┘                      │
└─────────────────────────────────────────────────────┘
       ▲                              │
  Source Groups                 Destination Groups
  (bot is admin)                (bot is member/admin)
```

**Runtime:** Python 3.11+, `python-telegram-bot` v20+ (async), polling mode.  
**Deployment:** Single `systemd` service on DigitalOcean droplet.

---

## Project Structure

```
bot-forward-msg-tele/
├── .env                          # BOT_TOKEN — never committed
├── config.yaml                   # All non-secret config
├── data/
│   └── masks.json                # Auto-generated anonymous ID assignments
├── main.py                       # Entry point
├── bot/
│   ├── config/
│   │   ├── loader.py             # Load and validate config.yaml into Config object
│   │   └── writer.py             # Persist runtime changes back to config.yaml
│   ├── handlers/
│   │   ├── message.py            # Receive all group messages, route to pipeline
│   │   └── commands.py           # Admin Telegram commands
│   ├── forwarder/
│   │   └── relay.py              # Format and send messages to destination
│   └── filters/
│       ├── type_filter.py        # Allow/block by message type
│       └── keyword_filter.py     # Allow/block by keyword in text
├── requirements.txt
└── deploy/
    └── telegram-forwarder.service  # systemd unit file
```

---

## Configuration

### `.env`
```env
BOT_TOKEN=your_bot_token_here
```

### `config.yaml`
```yaml
admins:
  - 123456789      # Whitelisted Telegram user IDs for admin commands
  - 987654321

masking:
  # Global defaults — applied to all pairs unless overridden
  users:
    111111111:
      alias: "Customer Alpha"    # Fixed alias (always shown as this name)
    222222222:
      alias: null                # Auto-numbered: "User #N" (consistent per pair)

pairs:
  - name: "customer-internal"
    group_a_chat_id: -1001234567890
    group_b_chat_id: -1009876543210
    bidirectional: true    # default: true. Set to false for one-way only (group_a → group_b)
    enabled: true
    filters:
      types:
        allow: [text, photo, video, sticker, document, voice, animation]
      keywords:
        block: []
        allow: []    # Empty = no allowlist; all non-blocked messages pass
    masking:
      a_to_b:        # Masking applied when forwarding Group A → Group B
        333333333:
          alias: "VIP Customer"
      b_to_a:        # Masking applied when forwarding Group B → Group A
        999999999:
          alias: "Support Agent"
```

---

## Message Pipeline

For every incoming message:

```
Message arrives in a group
        │
        ▼
Is sender == bot itself?
   YES → drop (loop prevention)
        │ NO
        ▼
Does this chat_id match any pair (group_a or group_b)?
   NO → ignore silently
        │ YES
        ▼
Is the pair enabled?
   NO → drop
        │ YES
        ▼
type_filter: Is this message type in the allow list?
   NO → drop
        │ YES
        ▼
keyword_filter: Does text pass keyword rules?
   Blocklist match → drop
   Allowlist set but no match → drop
        │ PASS
        ▼
masking: Resolve display name for this sender in this direction
   1. Check per-pair directional override (a_to_b or b_to_a)
   2. Check global masking.users
   3. Fall back to real display name
        │
        ▼
relay: Format as "<DisplayName>: <content>" and send to destination group
```

---

## Masking Engine

### Alias types

| Config | Displayed as |
|---|---|
| `alias: "User Alpha"` | `User Alpha: Hello` |
| `alias: null` | `User #3: Hello` (auto-numbered) |
| *(no entry)* | `John Smith: Hello` (real name) |

### Auto-numbering

Anonymous IDs are assigned on first message and stored in `data/masks.json`. Numbers are scoped per pair — the same user can be `User #1` in one pair and `User #4` in another.

```json
{
  "customer-internal": {
    "222222222": 1,
    "444444444": 2
  }
}
```

### Privacy guarantee

The destination group sees only aliases or anonymous IDs — never real Telegram user IDs or usernames. Admin commands expose only alias→number mappings, not real identities behind anonymous IDs.

### Masking resolution order

1. Per-pair directional override (`a_to_b` or `b_to_a`)
2. Global `masking.users`
3. Real display name (unmasked)

---

## Admin Commands

All commands are restricted to user IDs listed in `config.yaml → admins`. Unauthorized users receive no response.

| Command | Description |
|---|---|
| `/status` | List all pairs with enabled state and filter summary |
| `/enable <pair-name>` | Enable a forwarding pair |
| `/disable <pair-name>` | Pause a forwarding pair |
| `/filter <pair> block type <type>` | Add a message type to the block list |
| `/filter <pair> allow type <type>` | Add a message type to the allow list |
| `/filter <pair> block keyword <word>` | Add a keyword to the block list |
| `/filter <pair> allow keyword <word>` | Add a keyword to the allow list |
| `/filter <pair> remove keyword <word>` | Remove a keyword rule |
| `/mask <pair> <direction> <user_id> <alias>` | Set a fixed alias for a user. `<direction>`: `a_to_b`, `b_to_a`, or `global` |
| `/mask <pair> <direction> <user_id> anon` | Set a user to auto-numbered anonymous. Same direction values. |
| `/unmask <pair> <direction> <user_id>` | Remove masking for a user (show real name). Same direction values. |

All commands immediately persist changes to `config.yaml` and take effect without restart.

---

## Loop Prevention

The bot detects its own forwarded messages by checking `message.from_user.id == bot_id`. Any message sent by the bot account is silently dropped and not re-forwarded. This prevents bidirectional pairs from creating infinite forwarding loops.

---

## Relay Format

Messages are sent as new bot messages (not Telegram native forwards) to preserve sender privacy and allow masking.

**Text:**
```
CustomerAlpha: Hello everyone
```

**Media with caption:**
```
[photo sent]
CustomerAlpha: Check this out
```

**Media without caption:**
```
[photo sent by CustomerAlpha]
```

**Sticker/animation:** Forwarded as-is, preceded by a text message identifying the sender:
```
CustomerAlpha sent a sticker:
[sticker]
```

---

## Deployment

### systemd unit (`deploy/telegram-forwarder.service`)
```ini
[Unit]
Description=Telegram Message Forwarder Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/telegram-forwarder
EnvironmentFile=/opt/telegram-forwarder/.env
ExecStart=/opt/telegram-forwarder/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Commands
```bash
sudo systemctl enable telegram-forwarder
sudo systemctl start telegram-forwarder
sudo systemctl status telegram-forwarder
journalctl -u telegram-forwarder -f    # live logs
```

---

## Error Handling

- **Message send failure:** Log the error, skip the message, continue. Do not crash.
- **Invalid config:** Fail fast on startup with a clear error message.
- **Unknown chat ID:** Log a warning, ignore the message.
- **Unauthorized command:** Silently ignore (no response to prevent enumeration).
- **`masks.json` missing:** Auto-create on first write.

---

## Testing Strategy

- **Unit tests** for filter engine (type + keyword logic) and masking resolution with known inputs
- **Integration smoke test:** Send a test message to a staging group pair and verify it appears correctly in the destination
- No mocking of the Telegram API — use a separate test bot token against real test groups for integration tests
