# Telegram Message Forwarder Bot

A Telegram bot that monitors group pairs and forwards messages bidirectionally with configurable filters and sender masking.

## Features

- Bidirectional message forwarding between group pairs
- Supports text, photo, video, sticker, document, voice, and animation messages
- Keyword filter (block/allow lists, case-insensitive)
- Message type filter
- Sender masking — fixed alias or anonymous ID (`User #1`, `User #2`, ...)
- Per-pair directional masking overrides
- Admin commands to manage pairs, filters, and masks at runtime
- Loop prevention (bot's own forwarded messages are not re-forwarded)
- Runtime config changes persist to `config.yaml` without restart

## Requirements

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Privacy mode **disabled** for the bot (BotFather → `/setprivacy` → Disable)
- Bot added as a member to all configured groups

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set BOT_TOKEN=your_token_here
```

Edit `config.yaml` with your group chat IDs and admin user ID:

```yaml
admins:
  - 123456789  # Your Telegram user ID

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

> **Note:** Supergroup chat IDs start with `-100`. Use `getUpdates` or the debug log to find the real ID.

## Run

```bash
source venv/bin/activate
python main.py
```

## Admin Commands

All commands are restricted to user IDs listed under `admins` in `config.yaml`.

| Command | Description |
|---|---|
| `/status` | Show all pairs and their current state |
| `/enable <pair>` | Enable forwarding for a pair |
| `/disable <pair>` | Disable forwarding for a pair |
| `/filter <pair> <block\|allow\|remove> <type\|keyword> <value>` | Modify type or keyword filters |
| `/mask <pair> <a_to_b\|b_to_a\|global> <user_id> <alias\|anon>` | Set a display name or anonymise a user |
| `/unmask <pair> <a_to_b\|b_to_a\|global> <user_id>` | Remove masking for a user |

### Filter examples

```
/filter my-pair block type sticker
/filter my-pair allow keyword urgent
/filter my-pair remove keyword urgent
```

### Mask examples

```
/mask my-pair a_to_b 123456789 Alice        # fixed alias
/mask my-pair global 123456789 anon         # anonymous (User #N)
/unmask my-pair global 123456789
```

## Deployment (systemd / DigitalOcean)

Copy files to your server:

```bash
scp -r . ubuntu@your-server:/opt/telegram-forwarder
```

Install the service:

```bash
sudo cp deploy/telegram-forwarder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-forwarder
sudo systemctl start telegram-forwarder
sudo journalctl -u telegram-forwarder -f
```

## Project Structure

```
main.py                      # Entry point
config.yaml                  # Pair and filter configuration
bot/
  config/
    loader.py                # Load and validate config.yaml
    writer.py                # Persist runtime changes back to disk
  filters/
    type_filter.py           # Allow/block by message type
    keyword_filter.py        # Allow/block by keyword
  masking/
    engine.py                # Resolve display names and anonymous IDs
  forwarder/
    relay.py                 # Send messages to destination chat
  handlers/
    message.py               # Main pipeline handler
    commands.py              # Admin command handlers
data/
  masks.json                 # Auto-generated anonymous ID assignments
deploy/
  telegram-forwarder.service # systemd unit file
```

## Tests

```bash
source venv/bin/activate
pytest tests/ -v
```
