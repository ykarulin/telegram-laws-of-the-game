# Database Setup and Configuration

This document explains how to set up and manage the database for the Football Rules Expert Bot.

## Overview

The bot uses SQLite by default for development/testing, with full support for PostgreSQL in production. The database stores all messages and bot responses to maintain conversation history.

## Current Setup: SQLite (Default)

### Location
- **Development**: `conversations.db` in project root
- **Testing**: `test_conversations.db` (created/deleted by tests)
- **Production**: Recommended to upgrade to PostgreSQL

### Enable/Disable
By default, SQLite is used. No configuration needed for development.

## Production Setup: PostgreSQL with Docker

### Prerequisites
- Docker
- Docker Compose
- PostgreSQL 16 or later

### Quick Start

1. **Start PostgreSQL Container**
   ```bash
   docker compose up -d
   ```

2. **Initialize Schema**
   ```bash
   docker compose exec postgres psql -U telegram_bot telegram_bot_db -f migrations/001_initial_schema.sql
   ```

3. **Configure Bot**
   ```env
   DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db
   ```

4. **Verify Connection**
   ```bash
   docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"
   ```

## Database Schema

### Messages Table

```sql
CREATE TABLE messages (
    message_id BIGINT PRIMARY KEY,      -- Telegram message ID
    user_id BIGINT NOT NULL,            -- Telegram user ID
    text TEXT NOT NULL,                 -- User's message text
    bot_response TEXT NOT NULL,         -- Bot's response
    reply_to_message_id BIGINT,         -- Parent message ID
    timestamp DATETIME NOT NULL,        -- Message timestamp
    created_at DATETIME NOT NULL        -- DB record creation time
);
```

### Indexes

- `message_id` (Primary Key)
- `user_id` (Quick user lookup)
- `timestamp DESC` (Recent messages)
- `user_id, timestamp DESC` (User's recent messages)
- `reply_to_message_id` (Conversation chains)

## Configuration

### Environment Variables

```env
# Database connection string
# SQLite: sqlite:///conversations.db
# PostgreSQL: postgresql://user:password@host:port/database
DATABASE_URL=sqlite:///conversations.db

# For PostgreSQL with Docker Compose:
DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db

# For remote PostgreSQL (production):
DATABASE_URL=postgresql://telegram_bot:strong_password@your-host.com:5432/telegram_bot_db
```

### Example .env Files

#### Development
```env
DATABASE_URL=sqlite:///conversations.db
```

#### Testing
```env
DATABASE_URL=sqlite:///test_conversations.db
```

#### Production (with Docker Postgres)
```env
DATABASE_URL=postgresql://telegram_bot:your_password@localhost:5432/telegram_bot_db
```

## Database Operations

### Create Database Backup

```bash
# SQLite
cp conversations.db conversations.db.backup

# PostgreSQL
docker compose exec -T postgres pg_dump -U telegram_bot telegram_bot_db > backup.sql
```

### Restore from Backup

```bash
# SQLite
cp conversations.db.backup conversations.db

# PostgreSQL
docker compose exec postgres psql -U telegram_bot telegram_bot_db < backup.sql
```

### View Database Stats

```bash
# Total messages
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"

# Messages per user
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT user_id, COUNT(*) FROM messages GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 10;"

# Database size
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT pg_size_pretty(pg_database_size('telegram_bot_db'));"

# Recent messages
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT message_id, user_id, timestamp FROM messages ORDER BY timestamp DESC LIMIT 10;"
```

### Database Maintenance

```bash
# Vacuum (reclaim space)
docker compose exec postgres vacuumdb -U telegram_bot telegram_bot_db

# Analyze (update statistics)
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "ANALYZE;"

# Full maintenance
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "REINDEX DATABASE telegram_bot_db;"
```

## Migration: SQLite to PostgreSQL

If you're currently using SQLite and want to migrate to PostgreSQL:

### Step 1: Export from SQLite

```bash
# Export all messages
sqlite3 conversations.db ".mode insert messages" ".output export.sql" "SELECT * FROM messages;"
```

### Step 2: Create PostgreSQL Tables

```bash
# Initialize PostgreSQL with schema
docker compose exec postgres psql -U telegram_bot telegram_bot_db -f migrations/001_initial_schema.sql
```

### Step 3: Import Data

```bash
# Load the exported data
docker compose exec postgres psql -U telegram_bot telegram_bot_db -f export.sql
```

### Step 4: Update Configuration

```env
# Change DATABASE_URL to PostgreSQL
DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db
```

### Step 5: Verify

```bash
# Count messages in both databases
# SQLite: sqlite3 conversations.db "SELECT COUNT(*) FROM messages;"
# PostgreSQL: docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"

# Should match!
```

## Docker Compose Reference

### Configuration

The `docker-compose.yml` file defines:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: law-of-the-game-db
    environment:
      POSTGRES_USER: telegram_bot
      POSTGRES_PASSWORD: telegram_bot_password
      POSTGRES_DB: telegram_bot_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U telegram_bot"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### Common Commands

```bash
# Start PostgreSQL
docker compose up -d

# Stop PostgreSQL
docker compose down

# View logs
docker compose logs postgres

# Access PostgreSQL shell
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db

# Remove container and volumes (WARNING: deletes data!)
docker compose down -v

# Backup before removing
docker compose exec -T postgres pg_dump -U telegram_bot telegram_bot_db > backup.sql
docker compose down -v
```

## Performance Optimization

### For High-Volume Bots

Add these indexes:

```sql
-- User's recent messages
CREATE INDEX idx_messages_user_recent ON messages(user_id, timestamp DESC)
WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '30 days';

-- Conversation chains
CREATE INDEX idx_messages_chain ON messages(reply_to_message_id, timestamp);

-- Search
CREATE INDEX idx_messages_text ON messages USING GIN(to_tsvector('english', text));
```

### Query Optimization

```bash
# Use EXPLAIN to see query plans
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "EXPLAIN SELECT * FROM messages WHERE user_id = 123 ORDER BY timestamp DESC LIMIT 10;"
```

## Security

### SQLite (Development)

- Keep `conversations.db` out of version control
- Use `.gitignore`: `conversations.db`

### PostgreSQL (Production)

- Change default password in `docker-compose.yml`
- Use strong passwords (20+ characters)
- Restrict database access to localhost or internal network
- Use SSL/TLS for remote connections
- Regular backups to separate storage
- Enable audit logging if needed

### Connection Security

```env
# For remote PostgreSQL with SSL
DATABASE_URL=postgresql://telegram_bot:password@host:5432/telegram_bot_db?sslmode=require
```

## Troubleshooting

### SQLite

**File locked error**
- One process is accessing the database
- Close other applications
- Check for zombie processes: `lsof conversations.db`

**Database corrupted**
```bash
# Check database integrity
sqlite3 conversations.db "PRAGMA integrity_check;"

# Restore from backup
cp conversations.db.backup conversations.db
```

### PostgreSQL

**Connection refused**
```bash
# Check container is running
docker compose ps

# Check PostgreSQL logs
docker compose logs postgres

# Test connection
docker compose exec postgres pg_isready
```

**Authentication failed**
```bash
# Verify credentials in DATABASE_URL
# Check environment variable is set
echo $DATABASE_URL

# Test with psql
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT 1;"
```

**Disk full**
```bash
# Check disk space
df -h

# Check database size
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT pg_size_pretty(pg_database_size('telegram_bot_db'));"

# Clean old messages if needed
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "DELETE FROM messages WHERE timestamp < NOW() - INTERVAL '1 year';"
```

## Testing

The test suite uses a separate SQLite database:

```bash
# Run tests (uses test_conversations.db)
pytest tests/

# Tests automatically clean up after themselves
```

## Monitoring

### Regular Checks

```bash
# Bot status
sudo journalctl -u telegram-bot -f

# Database status
docker compose ps

# Message count
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"

# Active connections
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT count(*) FROM pg_stat_activity;"
```

## Support

For issues or questions:
- Check PostgreSQL logs: `docker compose logs postgres`
- Check bot logs: `sudo journalctl -u telegram-bot -f`
- Review this documentation
- Consult PostgreSQL documentation: https://www.postgresql.org/docs/

