# PostgreSQL Migration Guide

This guide explains how to migrate the Football Rules Expert Bot from SQLite to PostgreSQL using Docker.

## Overview

- **Current**: SQLite database (`conversations.db`)
- **Target**: PostgreSQL 16 with Docker
- **Effort**: ~15 minutes for fresh deployment
- **Data Migration**: Available for existing deployments

## Why PostgreSQL?

| Feature | SQLite | PostgreSQL |
|---------|--------|-----------|
| Concurrent Users | Limited | Excellent |
| Data Consistency | Good | Excellent |
| Scaling | Limited | Excellent |
| Backups | File copy | Point-in-time recovery |
| Monitoring | None | Full monitoring |
| Network Access | Local only | Local/Remote |
| High Availability | Not supported | Streaming replication |

## Fresh PostgreSQL Deployment (No Data)

### Prerequisites

```bash
# Check Docker is installed
docker --version
docker compose --version

# Should see versions like:
# Docker version 25.0.0
# Docker Compose version 2.24.0
```

### Step-by-Step

#### 1. Start PostgreSQL Container

```bash
cd /path/to/law-of-the-game
docker compose up -d

# Wait for it to be ready (should see health status "healthy")
docker compose ps
```

**Output should show:**
```
NAME                          STATUS
law-of-the-game-db        Up (healthy)
```

#### 2. Initialize Database Schema

```bash
docker compose exec postgres psql -U telegram_bot telegram_bot_db -f migrations/001_initial_schema.sql

# Verify tables were created
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "\dt"

# Should output:
#              List of relations
# Schema | Name | Type  |     Owner
# --------|-------|-------|----------------
# public | messages | table | telegram_bot
```

#### 3. Update Configuration

```bash
# Edit .env.development (or your environment file)
nano .env.development

# Add or uncomment:
DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db
```

#### 4. Start the Bot

```bash
source venv/bin/activate
python main.py

# Should see in logs:
# Database initialized successfully
# Starting bot with polling...
```

#### 5. Test It Works

In Telegram:
1. Send a message to the bot
2. Bot should respond after a few seconds
3. Check the message was stored:

```bash
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"
```

## Migrating Data from SQLite

If you have an existing SQLite database with messages, follow this process:

### Prerequisites

- Existing `conversations.db` file
- PostgreSQL container running
- `sqlite3` command line tool

### Migration Steps

#### 1. Export SQLite Data

```bash
# Create export SQL file
sqlite3 conversations.db << 'EOF' > sqlite_export.sql
SELECT 'INSERT INTO messages (message_id, user_id, text, bot_response, reply_to_message_id, timestamp) VALUES (' ||
       message_id || ', ' ||
       user_id || ', ' ||
       quote(text) || ', ' ||
       quote(bot_response) || ', ' ||
       quote(reply_to_message_id) || ', ' ||
       quote(timestamp) || ');'
FROM messages;
EOF

# Verify export was created
wc -l sqlite_export.sql  # Should show many lines
head sqlite_export.sql   # Should show INSERT statements
```

#### 2. Stop the Bot (If Running)

```bash
# If running as service
sudo systemctl stop telegram-bot

# If running in terminal, press Ctrl+C
```

#### 3. Initialize PostgreSQL Schema

```bash
docker compose exec postgres psql -U telegram_bot telegram_bot_db -f migrations/001_initial_schema.sql
```

#### 4. Import Data

```bash
# Import the exported data
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db < sqlite_export.sql

# Watch for progress - it will take a while for large databases
```

#### 5. Verify Data Was Imported

```bash
# Count messages
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) as total_messages FROM messages;"

# Compare with SQLite count
sqlite3 conversations.db "SELECT COUNT(*) FROM messages;"

# Should match!
```

#### 6. Verify Conversation Chains

```bash
# Check a specific user's messages
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT message_id, user_id, reply_to_message_id, timestamp FROM messages LIMIT 5;"

# Verify timestamps are preserved
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT MIN(timestamp), MAX(timestamp) FROM messages;"
```

#### 7. Backup Old SQLite

```bash
# Keep old SQLite as backup
mv conversations.db conversations.db.backup

# Archive it
tar czf conversations.db.backup.tar.gz conversations.db.backup
```

#### 8. Update Configuration

```bash
# Edit .env file
DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db
```

#### 9. Restart Bot

```bash
# If using systemd
sudo systemctl start telegram-bot

# If running manually
source venv/bin/activate
python main.py
```

#### 10. Monitor for Errors

```bash
# Check logs
sudo journalctl -u telegram-bot -f

# Bot should start without errors and recognize existing data
```

## Verification Checklist

After migration, verify everything works:

```bash
# ✓ Container is running
docker compose ps
# Status should be "Up"

# ✓ Database accessible
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT 1"
# Should output: 1

# ✓ Messages were imported
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"
# Should match SQLite count

# ✓ Bot is running
sudo systemctl status telegram-bot
# Should show "active (running)"

# ✓ Bot can respond
# Send message in Telegram, verify you get a response

# ✓ New messages are stored
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT message_id, timestamp FROM messages ORDER BY timestamp DESC LIMIT 1;"
# Should show your recent message

# ✓ Conversation chains work
# Reply to an old message in Telegram, bot should include context
```

## Rollback Plan

If something goes wrong, you can roll back:

```bash
# Stop the bot
sudo systemctl stop telegram-bot

# Stop PostgreSQL
docker compose down

# Remove PostgreSQL container (data will be preserved in volume)
docker compose down

# Go back to SQLite (if you still have the backup)
# Update .env to remove DATABASE_URL or use SQLite path

# Restart bot
python main.py
```

## Common Issues During Migration

### Issue: "permission denied" when accessing SQLite

**Solution:**
```bash
# Check file permissions
ls -la conversations.db

# Make readable
chmod 644 conversations.db
```

### Issue: "syntax error" in exported data

**Solution:**
```bash
# Use different export method (may have special characters)
sqlite3 -json conversations.db "SELECT * FROM messages" > export.json

# Then write Python script to convert JSON to SQL
```

### Issue: Data isn't appearing in PostgreSQL

**Solution:**
```bash
# Check PostgreSQL received the INSERT commands
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"

# If zero, check for errors in import:
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db < sqlite_export.sql 2>&1 | head -20
```

### Issue: Timestamp column has different format

**Solution:**
```bash
# PostgreSQL might interpret timestamps differently
# Check the values:
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT timestamp, typeof(timestamp) FROM messages LIMIT 1;"

# If you see NULL or wrong values, you may need to:
# 1. Re-export with proper timestamp formatting
# 2. Or accept the data as-is (timestamps will reset)
```

## Performance After Migration

Check if PostgreSQL is performing well:

```bash
# Check query execution times
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "EXPLAIN ANALYZE SELECT * FROM messages WHERE user_id = 12345 ORDER BY timestamp DESC LIMIT 10;"

# Check index usage
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT schemaname, tablename, indexname FROM pg_indexes WHERE tablename = 'messages';"

# Monitor active queries
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT pid, usename, query FROM pg_stat_activity WHERE state = 'active';"
```

## Next Steps After Migration

### Backup Strategy

```bash
# Daily backup
docker compose exec -T postgres pg_dump -U telegram_bot telegram_bot_db > backup_$(date +%Y%m%d).sql

# Store backups securely
mv backup_*.sql /backup/location/
```

### Monitoring

```bash
# Monitor database size
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT pg_size_pretty(pg_database_size('telegram_bot_db')) as size;"

# Monitor message growth
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"
```

### Maintenance

```bash
# Weekly vacuum and analyze
docker compose exec postgres vacuumdb -U telegram_bot telegram_bot_db
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "ANALYZE;"
```

## Production Considerations

### Change Default Password

In `docker-compose.yml`, replace:
```yaml
POSTGRES_PASSWORD: telegram_bot_password
```

With a strong password.

### Remote Database

For cloud deployment, use:
```env
DATABASE_URL=postgresql://telegram_bot:password@db.example.com:5432/telegram_bot_db
```

### SSL/TLS

For secure remote connections:
```env
DATABASE_URL=postgresql://telegram_bot:password@db.example.com:5432/telegram_bot_db?sslmode=require
```

### Connection Pooling

For high-traffic bots, add PgBouncer later.

## Support

If you encounter issues:

1. Check PostgreSQL logs:
   ```bash
   docker compose logs postgres
   ```

2. Check bot logs:
   ```bash
   sudo journalctl -u telegram-bot -f
   ```

3. Test database connection:
   ```bash
   docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT 1"
   ```

4. Review [DATABASE_SETUP.md](DATABASE_SETUP.md) for more help

