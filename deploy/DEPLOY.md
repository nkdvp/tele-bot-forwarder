# Deployment Guide

## Prerequisites

- Ubuntu server with SSH access
- Bot token from [@BotFather](https://t.me/BotFather)
- Privacy mode disabled for the bot (BotFather → `/setprivacy` → Disable)

---

## First-time Setup

**1. Copy files to the server**

```bash
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='.git' --exclude='.env' --exclude='data/' ./ root@YOUR_SERVER_IP:/opt/telegram-forwarder/
```

**2. SSH into the server**

```bash
ssh root@YOUR_SERVER_IP
```

**3. Install Python and dependencies**

```bash
apt update && apt install -y python3 python3-venv python3-pip
cd /opt/telegram-forwarder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p data
```

**4. Create `.env`**

```bash
echo "BOT_TOKEN=your_bot_token_here" > /opt/telegram-forwarder/.env
```

**5. Install and start the service**

```bash
cp /opt/telegram-forwarder/deploy/telegram-forwarder.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable telegram-forwarder
systemctl start telegram-forwarder
```

**6. Verify it's running**

```bash
systemctl status telegram-forwarder
journalctl -u telegram-forwarder -f
```

Expected output: `Bot started. Polling...`

---

## Redeployment

After making changes locally, copy the updated files and restart:

```bash
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='.git' --exclude='.env' --exclude='data/' ./ root@YOUR_SERVER_IP:/opt/telegram-forwarder/
ssh root@YOUR_SERVER_IP "systemctl restart telegram-forwarder"
```

---

## Useful Commands

```bash
# View live logs
journalctl -u telegram-forwarder -f

# Restart the bot
systemctl restart telegram-forwarder

# Stop the bot
systemctl stop telegram-forwarder

# Check status
systemctl status telegram-forwarder
```

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
