# Telegram Message Forwarder Bot

A Telegram bot that forwards messages between group pairs with configurable filters, sender masking, and runtime admin commands.

## Features

- Bidirectional message forwarding between group pairs
- Supports text, photo, video, sticker, document, voice, and animation messages
- Keyword filter (block/allow lists, case-insensitive)
- Message type filter
- Sender masking — fixed alias or anonymous ID (`User #1`, `User #2`, ...)
- Per-pair directional masking overrides
- Loop prevention (bot's own forwarded messages are not re-forwarded)
- **v2:** Rate limiting — queues API calls, never drops messages
- **v2:** Health endpoint at `GET /health` (pingable by UptimeRobot)
- **v2:** Startup/shutdown alerts via Telegram DM
- **v2:** Message recovery — replays buffered messages on restart, skips anything older than N minutes
- **v2:** Runtime `/set`, `/admin`, `/pair` commands — change config without editing YAML
- **v2:** Auto group ID discovery — bot DMs you the chat ID when added to a group
- **v2:** `/stats` — forwarded message counts per pair (today / this week)
- Runtime config changes persist to `config.yaml` without restart

## Requirements

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Privacy mode **disabled** (BotFather → `/setprivacy` → Disable)
- Bot added as a member to all configured groups

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set BOT_TOKEN and any optional DB/admin settings
```

Edit `config.yaml`:

```yaml
admins:
  - 123456789  # Your Telegram user ID

recovery_window_minutes: 15  # skip messages older than this on restart (0 = replay all)

monitoring:                  # remove block to disable alerts
  alert_chat_id: 123456789   # your user ID for DMs, or a group chat ID

masking:
  users: {}

pairs:
  - name: "my-pair"
    group_a_chat_id: -1001111111111
    group_b_chat_id: -1002222222222
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

> **Tip:** Supergroup chat IDs start with `-100`. Add the bot to the group and it will DM you the chat ID automatically (v2 auto-discovery).

## Run

```bash
source venv/bin/activate
python main.py
```

### Recommended `.env`-driven run (no manual `export`)

Put your runtime settings in `.env` (already loaded by `main.py`):

```env
BOT_TOKEN=...
HEALTH_PORT=8080
USE_DB_CONFIG=true
DB_PATH=data/forwarder.db
ADMIN_PORT=8090
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
```

Then run normally:

```bash
source venv/bin/activate
python main.py
```

If `USE_DB_CONFIG=true`, run migration once first:

```bash
python -m bot.storage.db_migration \
  --config config.yaml \
  --reply-map data/reply_map.json \
  --db data/forwarder.db \
  --dry-run

python -m bot.storage.db_migration \
  --config config.yaml \
  --reply-map data/reply_map.json \
  --db data/forwarder.db
```

On first start the bot registers its command menu with Telegram — type `/` in any chat with the bot to see all available commands.

## Web Admin UX Notes

- Default UI language is **Tiếng Việt**. You can switch between Vietnamese and English from the top bar.
- Theme can be switched between **dark** and **light** in the top bar; preference is remembered per browser.
- Navigation is role-aware:
  - `super_admin` / `admin`: can see Backups, Users, Teams.
  - `user`: these admin-only sections are hidden and access remains blocked server-side.
- Pair masking in the web UI is shown as one logical mapping per user ("Telegram user -> masked output"), while bidirectional storage is handled internally.

## Admin Commands

All commands are restricted to user IDs in `admins`. They work in any private or group chat the bot is a member of.

### Pair management

| Command | Description |
|---|---|
| `/status` | Show all pairs and their current state |
| `/enable <pair>` | Enable forwarding for a pair |
| `/disable <pair>` | Disable forwarding for a pair |
| `/pair add <name> <group_a_id> <group_b_id> [true\|false]` | Add a new pair (bidirectional by default) |
| `/pair remove <name>` | Remove a pair |

### Stats

| Command | Description |
|---|---|
| `/stats` | Message counts for all pairs (today / this week) |
| `/stats <pair>` | Counts for a specific pair |

### Settings

| Command | Description |
|---|---|
| `/set recovery_window <minutes>` | Set the message age filter (0 = disabled) |
| `/set alert_chat <chat_id>` | Set where startup/shutdown alerts are sent |

### Admin management

| Command | Description |
|---|---|
| `/admin add <user_id>` | Add a new admin |
| `/admin remove <user_id>` | Remove an admin (cannot remove yourself or the last admin) |

### Filters & masking

| Command | Description |
|---|---|
| `/filter <pair> block type <type>` | Block a message type |
| `/filter <pair> allow type <type>` | Allow a message type |
| `/filter <pair> block keyword <word>` | Block messages containing a keyword |
| `/filter <pair> allow keyword <word>` | Allow only messages containing a keyword |
| `/filter <pair> remove keyword <word>` | Remove a keyword rule |
| `/mask <pair> <a_to_b\|b_to_a\|global> <user_id> <alias\|anon>` | Set display name or anonymise |
| `/unmask <pair> <a_to_b\|b_to_a\|global> <user_id>` | Remove masking |

### Examples

```
# Add a new pair discovered via auto-discovery DM
/pair add support -1009111111111 -1009222222222

# Block stickers on a pair
/filter support block type sticker

# Give a user a fixed alias
/mask support a_to_b 123456789 Alice

# Check forwarding counts
/stats support

# Change the message recovery window
/set recovery_window 30
```

## Deployment (systemd / DigitalOcean)

See [`deploy/DEPLOY.md`](deploy/DEPLOY.md) for full instructions including health monitoring setup with UptimeRobot.

Quick redeploy:

```bash
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='.git' --exclude='.env' --exclude='data/' ./ root@YOUR_SERVER_IP:/opt/telegram-forwarder/
ssh root@YOUR_SERVER_IP "systemctl restart telegram-forwarder"
```

## Project Structure

```
main.py                       # Entry point — wires all handlers, rate limiter, health server
config.yaml                   # Pair and filter configuration
bot/
  config/
    loader.py                 # Load and validate config.yaml
    writer.py                 # Persist runtime changes back to disk
  filters/
    type_filter.py            # Allow/block by message type
    keyword_filter.py         # Allow/block by keyword
  masking/
    engine.py                 # Resolve display names and anonymous IDs
  forwarder/
    relay.py                  # Send messages to destination chat
  handlers/
    message.py                # Main pipeline: age filter → pair lookup → relay → stats
    commands.py               # Admin command handlers
    membership.py             # Auto group ID discovery on bot join
  health/
    server.py                 # aiohttp GET /health endpoint
  stats/
    counter.py                # Per-pair forwarded message counts (data/stats.json)
data/
  masks.json                  # Auto-generated anonymous ID assignments
  stats.json                  # Message count persistence
deploy/
  telegram-forwarder.service  # systemd unit file
  DEPLOY.md                   # Deployment and monitoring guide
```

## Tests

```bash
source venv/bin/activate
pytest tests/ -v
```
