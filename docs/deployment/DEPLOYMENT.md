# Production Deployment Guide

This guide covers deploying the Football Rules Expert Bot to production on a VPS with PostgreSQL.

## Quick Start for Production

### 1. Start PostgreSQL

```bash
docker compose up -d
```

### 2. Initialize Database

```bash
docker compose exec postgres psql -U telegram_bot telegram_bot_db -f migrations/001_initial_schema.sql
```

### 3. Configure Environment

```bash
# Edit .env.production with your credentials
DATABASE_URL=postgresql://telegram_bot:your_password@localhost:5432/telegram_bot_db
```

### 4. Start Bot

```bash
python main.py
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

```env
ENVIRONMENT=production
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-5-mini
OPENAI_MAX_TOKENS=4096
OPENAI_TEMPERATURE=1
LOG_LEVEL=INFO
DATABASE_URL=postgresql://telegram_bot:password@localhost:5432/telegram_bot_db
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

