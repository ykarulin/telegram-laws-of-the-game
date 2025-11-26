# Production Deployment Guide

This guide covers deploying the Football Rules Expert Bot to production on a VPS with PostgreSQL and optional webhook support.

## Quick Start for Production (Polling Mode)

### 1. Start PostgreSQL & Qdrant

```bash
docker compose up -d
```

### 2. Configure Environment

```bash
# Copy and edit .env.production with your credentials
cp .env.example .env.production
nano .env.production

# Set these required values:
ENVIRONMENT=production
TELEGRAM_BOT_TOKEN=your_actual_token
OPENAI_API_KEY=your_actual_key
DATABASE_URL=postgresql://telegram_bot:your_password@localhost:5432/telegram_bot_db
QDRANT_HOST=qdrant
QDRANT_PORT=6333
```

### 3. Start Bot (Polling Mode - No Domain Needed)

```bash
docker build -t telegram-bot:latest .
docker run -d --network host --env-file .env.production --name telegram-bot telegram-bot:latest
```

### 4. Sync Documents

```bash
docker run -it --network host --env-file .env.production telegram-bot:latest python -m src.cli.document_sync
```

## Full Production Setup

### System Requirements

- VPS with Docker & Docker Compose
- Python 3.13+
- 2GB+ RAM (1GB for bot, 1GB for PostgreSQL)
- 20GB+ disk space

### Installation

```bash
# 1. Install dependencies
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 2. Create app user and directory
sudo useradd -m -s /bin/bash telegram_bot
sudo mkdir -p /opt/telegram-bot
sudo chown telegram_bot:telegram_bot /opt/telegram-bot

# 3. Clone project
cd /opt/telegram-bot
git clone <repo-url> .
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Start PostgreSQL
docker compose up -d

# 5. Initialize database
docker compose exec postgres psql -U telegram_bot telegram_bot_db -f migrations/001_initial_schema.sql

# 6. Configure .env.production
# Set: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, DATABASE_URL

# 7. Start bot service (see systemd setup below)
```

### Systemd Service Setup

Save this as `/etc/systemd/system/telegram-bot.service`:

```ini
[Unit]
Description=Football Rules Expert Telegram Bot
After=network.target docker.service

[Service]
Type=simple
User=telegram_bot
WorkingDirectory=/opt/telegram-bot
ExecStart=/opt/telegram-bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot

# Monitor
sudo journalctl -u telegram-bot -f
```

## PostgreSQL with Docker Compose

The `docker-compose.yml` includes:

- PostgreSQL 16-Alpine image
- Persistent volume at `postgres_data/`
- Default credentials (change in production!)
- Health checks
- Port 5432 (internal only)

### Backup

```bash
# Daily backup
docker compose exec -T postgres pg_dump -U telegram_bot telegram_bot_db > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec postgres psql -U telegram_bot telegram_bot_db < backup.sql
```

## Environment Configuration

Set these in `.env.production`:

### Polling Mode (Simpler, recommended for testing)
```env
ENVIRONMENT=production
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4-turbo
OPENAI_MAX_TOKENS=4096
OPENAI_TEMPERATURE=0.7
LOG_LEVEL=INFO
DATABASE_URL=postgresql://telegram_bot:password@localhost:5432/telegram_bot_db
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=football_documents

# Leave webhook settings empty for polling mode
# TELEGRAM_WEBHOOK_URL=
# TELEGRAM_WEBHOOK_PORT=8443
# TELEGRAM_WEBHOOK_SECRET_TOKEN=
```

### Webhook Mode (Production recommended, requires domain + SSL)
```env
ENVIRONMENT=production
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4-turbo
OPENAI_MAX_TOKENS=4096
OPENAI_TEMPERATURE=0.7
LOG_LEVEL=INFO
DATABASE_URL=postgresql://telegram_bot:password@localhost:5432/telegram_bot_db
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=football_documents

# Webhook mode (requires domain)
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook
TELEGRAM_WEBHOOK_PORT=8443
TELEGRAM_WEBHOOK_SECRET_TOKEN=your_secret_token_here
```

## Webhook Setup with Telegram Bot API

If using webhook mode (recommended for production), you need to register the webhook URL with Telegram.

### Prerequisites
- Domain name pointing to your VPS
- SSL certificate (Let's Encrypt recommended)
- Bot already running and listening on the webhook port

### Step 1: Get SSL Certificate

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate for your domain
sudo certbot certonly --standalone -d your-domain.com

# Certificate files will be at:
# /etc/letsencrypt/live/your-domain.com/fullchain.pem
# /etc/letsencrypt/live/your-domain.com/privkey.pem
```

### Step 2: Set Up Reverse Proxy (Nginx)

Create `/etc/nginx/sites-available/telegram-bot`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /webhook {
        proxy_pass http://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 3: Start Bot with Webhook Configuration

```bash
# Update .env.production with webhook settings
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook
TELEGRAM_WEBHOOK_PORT=8443
TELEGRAM_WEBHOOK_SECRET_TOKEN=your_secret_token_here

# Start bot
docker run -d --network host --env-file .env.production --name telegram-bot telegram-bot:latest
```

### Step 4: Register Webhook with Telegram Bot API

Once your bot is running and listening, register the webhook URL:

```bash
# Make this API call (replace YOUR_BOT_TOKEN and your-domain.com)
curl -X POST \
  https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/webhook",
    "secret_token": "your_secret_token_here",
    "allowed_updates": ["message", "callback_query", "inline_query"],
    "max_connections": 100,
    "drop_pending_updates": false
  }'
```

Expected response:
```json
{
  "ok": true,
  "result": true,
  "description": "Webhook was set"
}
```

### Step 5: Verify Webhook Registration

```bash
# Check webhook info
curl -X GET \
  https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo
```

Expected response:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-domain.com/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "max_connections": 100,
    "allowed_updates": ["message", "callback_query", "inline_query"]
  }
}
```

### Step 6: Remove Webhook and Return to Polling (if needed)

```bash
# Delete webhook
curl -X POST \
  https://api.telegram.org/botYOUR_BOT_TOKEN/deleteWebhook

# Then restart bot without webhook configuration
# The bot will automatically switch to polling mode
```

## Monitoring

```bash
# Bot status
sudo systemctl status telegram-bot

# Bot logs
sudo journalctl -u telegram-bot -f

# Database status
docker compose ps

# Message count
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"

# Disk usage
df -h
```

## Security Notes

1. Change default PostgreSQL password in `docker-compose.yml`
2. Use strong API keys
3. Keep `.env` files secure (not in git)
4. Use firewall to restrict database access
5. Regular backups to separate location
6. Monitor resource usage

## Troubleshooting

### Webhook Issues

**Webhook not being called**
```bash
# Check webhook status
curl -X GET https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo

# Check if bot is listening on port 8443
sudo netstat -tlnp | grep 8443

# Check bot logs for errors
docker logs telegram-bot

# If nginx is forwarding, check nginx status
sudo systemctl status nginx
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

**Webhook returns 403/401**
```bash
# Verify secret token matches
# In .env.production:
TELEGRAM_WEBHOOK_SECRET_TOKEN=your_secret_token_here

# Must match exactly in setWebhook call:
# "secret_token": "your_secret_token_here"

# Restart bot after changing token
docker restart telegram-bot
```

**SSL Certificate Issues**
```bash
# Verify certificate is valid
curl -I https://your-domain.com/webhook

# Check certificate expiration
sudo certbot certificates

# Renew certificate
sudo certbot renew

# Telegram requires valid SSL - check with:
curl --cacert /etc/letsencrypt/live/your-domain.com/chain.pem \
  https://your-domain.com/webhook
```

### Polling Mode Fallback
```bash
# If webhook is not working, the bot will NOT automatically switch to polling
# You must manually delete the webhook:

curl -X POST https://api.telegram.org/botYOUR_BOT_TOKEN/deleteWebhook

# Then remove webhook settings from .env.production:
# TELEGRAM_WEBHOOK_URL=
# TELEGRAM_WEBHOOK_PORT=
# TELEGRAM_WEBHOOK_SECRET_TOKEN=

# Restart bot
docker restart telegram-bot

# Bot will now use polling mode
```

### Bot won't start
```bash
# Check for errors
sudo journalctl -u telegram-bot -n 50
# Check if port is in use
lsof -i :5432
```

### Database connection refused
```bash
# Check container status
docker compose ps
# Check logs
docker compose logs postgres
# Test connection
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT 1"
```

### High CPU/Memory
```bash
# Check database size
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"
# Run maintenance
docker compose exec postgres vacuumdb -U telegram_bot telegram_bot_db
```

## Maintenance

Daily:
```bash
# Check status
sudo systemctl status telegram-bot
```

Weekly:
```bash
# Backup database
docker compose exec -T postgres pg_dump -U telegram_bot telegram_bot_db > backup_$(date +%Y%m%d).sql.gz

# Check logs for errors
sudo journalctl -u telegram-bot --since "7 days ago" | grep -i error
```

Monthly:
```bash
# Database maintenance
docker compose exec postgres vacuumdb -U telegram_bot telegram_bot_db

# Update packages
sudo apt update && apt upgrade -y
```

