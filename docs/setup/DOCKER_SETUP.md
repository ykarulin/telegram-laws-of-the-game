# Docker Setup

Using Docker Compose to run PostgreSQL and Qdrant services.

## Overview

The project uses Docker Compose to manage two services:
- **PostgreSQL**: Stores conversation history and document metadata
- **Qdrant**: Vector database for semantic search

## Quick Start

```bash
# Start both services
make docker-up

# Stop both services (data persists)
make docker-down

# View logs
make docker-logs
```

## What is Configured

### docker-compose.yml

Services are defined in `docker-compose.yml`:

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

  qdrant:
    image: qdrant/qdrant:latest
    container_name: law-of-the-game-qdrant
    ports:
      - "6333:6333"  # gRPC API
      - "6334:6334"  # HTTP API (optional)
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]

volumes:
  postgres_data:
  qdrant_data:
```

## Data Persistence

### Understanding Docker Volumes

Data is stored in Docker-managed volumes:
- `postgres_data` → PostgreSQL database
- `qdrant_data` → Qdrant vector storage

**Important:**
- `make docker-down` → Services stop, data **persists** ✓
- `docker-compose down -v` → Services stop, volumes **deleted** ✗ (destructive)

### Example Lifecycle

```
Day 1:
  make docker-up          → PostgreSQL and Qdrant start
  → Use bot → Upload documents
  make docker-down        → Services stop, data in volumes

Day 2:
  make docker-up          → Services restart
  → Your data is still there! ✓
```

## Makefile Commands

```bash
# Start services in background
make docker-up

# Stop services (data persists)
make docker-down

# View all service logs (live)
make docker-logs

# View just Qdrant logs
make docker-logs-qdrant

# View just PostgreSQL logs
make docker-logs-postgres

# Rebuild Docker images (if Dockerfile changes)
make docker-build
```

## Common Tasks

### Check Service Status

```bash
docker-compose ps

# Output:
# NAME                      STATUS          PORTS
# law-of-the-game-db        Up (healthy)    5432->5432/tcp
# law-of-the-game-qdrant    Up (healthy)    6333->6333/tcp
```

### View Service Logs

```bash
# All services
make docker-logs

# Just Qdrant
make docker-logs-qdrant
docker-compose logs -f qdrant

# Just PostgreSQL
make docker-logs-postgres
docker-compose logs -f postgres
```

### Verify Services are Responding

```bash
# PostgreSQL
docker-compose exec postgres pg_isready -U telegram_bot

# Qdrant
curl http://localhost:6333/health
# Response: {"status":"ok"}
```

### Restart a Service

```bash
# Restart just Qdrant
docker-compose restart qdrant

# Restart just PostgreSQL
docker-compose restart postgres

# Restart everything
make docker-down
make docker-up
```

## Troubleshooting

### Services Won't Start

Check logs:
```bash
make docker-logs
```

Common issues:
- **Port already in use**: See "Port Conflicts" below
- **Image download fails**: Check internet connection
- **Disk full**: Free up disk space

### Port Conflicts

```bash
# Find what's using port 5432 (PostgreSQL)
lsof -i :5432

# Find what's using port 6333 (Qdrant)
lsof -i :6333

# Kill the conflicting process
kill -9 <PID>
```

### High Memory Usage

Limit Docker resources in docker-compose.yml:

```yaml
services:
  qdrant:
    mem_limit: 2g
    memswap_limit: 2g
```

Then restart:
```bash
make docker-down
make docker-up
```

### Database Connection Errors

```bash
# Make sure PostgreSQL is ready
docker-compose logs postgres

# Wait for "ready to accept connections" message
# Then run bot
make run-dev
```

### "Cannot connect to Qdrant"

```bash
# Verify Qdrant is running
docker-compose ps qdrant

# Check if responding
curl http://localhost:6333/health

# View logs
make docker-logs-qdrant
```

## Advanced Topics

### Inspecting Docker Volumes

```bash
# List all volumes
docker volume ls

# Inspect a volume
docker volume inspect postgres_data

# View volume size
du -sh /var/lib/docker/volumes/postgres_data/_data
```

### Backup and Restore

**Backup PostgreSQL:**
```bash
docker-compose exec postgres pg_dump \
  -U telegram_bot telegram_bot_db > backup.sql
```

**Restore PostgreSQL:**
```bash
docker-compose exec -T postgres psql \
  -U telegram_bot telegram_bot_db < backup.sql
```

**Backup Qdrant:**
```bash
docker run --rm \
  -v qdrant_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/qdrant_backup.tar.gz /data
```

### Connecting to Services Directly

**PostgreSQL:**
```bash
docker-compose exec postgres psql \
  -U telegram_bot -d telegram_bot_db
```

**Qdrant API:**
```bash
# View collections
curl http://localhost:6333/collections

# View collection info
curl http://localhost:6333/collections/football_documents
```

## Environment-Specific Setup

By default, `docker-compose up` uses `.env.development` which points to:
- `DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db`
- `QDRANT_HOST=localhost`
- `QDRANT_PORT=6333`

For other environments, update the corresponding `.env.testing` or `.env.production` files.

## See Also

- [Qdrant Setup](../vector-search/QDRANT_SETUP.md) - Qdrant server configuration
- [Database Setup](DATABASE_SETUP.md) - Database initialization
- [Environment Setup](ENVIRONMENTS.md) - Configuration files
