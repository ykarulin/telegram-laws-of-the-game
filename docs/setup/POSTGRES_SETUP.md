# PostgreSQL Setup Guide

This guide explains how to set up PostgreSQL for the Football Rules Expert Bot, using Docker for ease of deployment.

## Prerequisites

- Docker and Docker Compose installed
- The bot project files

## Quick Start

### 1. Start PostgreSQL Container

```bash
docker compose up -d
```

This will:
- Start a PostgreSQL 16 container named `law-of-the-game-db`
- Create the database `telegram_bot_db`
- Create the user `telegram_bot` with password `telegram_bot_password`
- Expose PostgreSQL on port 5432
- Use persistent volume storage for data

### 2. Initialize the Database Schema

PostgreSQL container is now running. Initialize the database schema by running:

```bash
psql -h localhost -U telegram_bot -d telegram_bot_db -f migrations/001_initial_schema.sql
```

When prompted for password, enter: `telegram_bot_password`

### 3. Configure the Bot

Update your `.env` files to use PostgreSQL:

For development (`.env.development`):
```env
DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db
```

For production (`.env.production`):
```env
DATABASE_URL=postgresql://telegram_bot:your_secure_password@your-host:5432/telegram_bot_db
```

For testing (`.env.testing`):
```env
DATABASE_URL=sqlite:///test_conversations.db
```

### 4. Verify Connection

Test the database connection:

```bash
psql -h localhost -U telegram_bot -d telegram_bot_db -c "SELECT version();"
```

## Docker Compose Commands

### Start containers
```bash
docker compose up -d
```

### Stop containers
```bash
docker compose down
```

### View logs
```bash
docker compose logs postgres
```

### Access PostgreSQL shell
```bash
docker compose exec postgres psql -U telegram_bot -d telegram_bot_db
```

### Remove containers and volumes (⚠️ WARNING: Deletes data)
```bash
docker compose down -v
```

## Database Schema

The current schema includes:

### `messages` table

| Column | Type | Notes |
|--------|------|-------|
| `message_id` | INTEGER | Telegram message ID (Primary Key) |
| `user_id` | INTEGER | Telegram user ID (Indexed) |
| `text` | TEXT | User's message |
| `bot_response` | TEXT | Bot's response |
| `reply_to_message_id` | INTEGER | Reference to parent message (Foreign Key) |
| `timestamp` | DATETIME | Message creation time (Indexed) |

**Indexes:**
- Primary Key: `message_id`
- Index on: `user_id` (for fast per-user queries)
- Index on: `timestamp` (for sorting recent messages)
- Foreign Key: `reply_to_message_id` references `messages(message_id)`

## Backup and Restore

### Create a backup

```bash
docker compose exec postgres pg_dump -U telegram_bot telegram_bot_db > backup.sql
```

### Restore from backup

```bash
docker compose exec -T postgres psql -U telegram_bot telegram_bot_db < backup.sql
```

## Environment Variables

Configure database connection via environment variables:

- `DATABASE_URL`: PostgreSQL connection string
  - Format: `postgresql://user:password@host:port/database`
  - Default: Uses SQLite if not set

## Monitoring

### Check PostgreSQL Status

```bash
docker compose ps
```

### Monitor Container Logs

```bash
docker compose logs -f postgres
```

### Check Disk Usage

```bash
docker compose exec postgres du -sh /var/lib/postgresql/data
```

## Production Deployment

For production:

1. **Use strong credentials**:
   - Replace default `telegram_bot_password` with a secure password
   - Update `POSTGRES_PASSWORD` in `docker-compose.yml`

2. **Network isolation**:
   - Don't expose port 5432 to public internet
   - Use private network between bot and database

3. **Persistent storage**:
   - Mount volumes to persistent locations
   - Regular backups using pg_dump

4. **Connection pooling**:
   - For high-traffic bots, consider using PgBouncer
   - Limits on concurrent connections prevent resource exhaustion

5. **SSL/TLS**:
   - Enable SSL connections for remote databases
   - Use connection string with `sslmode=require`

## Troubleshooting

### Connection refused

```bash
# Check if container is running
docker compose ps

# Check logs
docker compose logs postgres
```

### Permission denied on database

```bash
# Verify user has correct permissions
docker compose exec postgres psql -U postgres -d telegram_bot_db \
  -c "SELECT datname, usename FROM pg_database, pg_user WHERE datdba = usesysid;"
```

### Disk space issues

```bash
# Check container disk usage
docker system df

# Clean up old images/volumes
docker system prune
```

## Migration Strategy

To migrate from SQLite to PostgreSQL:

1. Export data from SQLite
2. Load schema into PostgreSQL
3. Import data
4. Update connection string in bot configuration
5. Test thoroughly in staging

Example migration script:

```python
import sqlite3
import psycopg2
from datetime import datetime

# Connect to SQLite
sqlite_conn = sqlite3.connect('conversations.db')
sqlite_cursor = sqlite_conn.cursor()

# Connect to PostgreSQL
pg_conn = psycopg2.connect(
    host="localhost",
    user="telegram_bot",
    password="telegram_bot_password",
    database="telegram_bot_db"
)
pg_cursor = pg_conn.cursor()

# Copy all messages
sqlite_cursor.execute("SELECT * FROM messages")
for row in sqlite_cursor.fetchall():
    pg_cursor.execute("""
        INSERT INTO messages (message_id, user_id, text, bot_response, reply_to_message_id, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, row)

pg_conn.commit()
pg_conn.close()
sqlite_conn.close()
```

## Performance Tuning

For production databases with high message volumes:

### Index optimization

```sql
-- Additional indexes for common queries
CREATE INDEX idx_messages_user_id_timestamp ON messages(user_id, timestamp DESC);
CREATE INDEX idx_messages_reply_chain ON messages(reply_to_message_id);
```

### Connection pooling configuration

```bash
# In docker-compose.yml, add environment variables for tuning
environment:
  POSTGRES_INIT_ARGS: "-c shared_buffers=256MB -c effective_cache_size=1GB"
```

## Next Steps

After PostgreSQL is set up:

1. Run tests to verify database integration: `pytest tests/`
2. Start the bot: `python main.py`
3. Monitor logs for any database-related errors

