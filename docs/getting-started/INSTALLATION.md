# Installation Guide

Complete step-by-step instructions for setting up the Football Rules Bot.

## Prerequisites

Before starting, ensure you have:

1. **Python 3.13+**
   ```bash
   python --version  # Should be 3.13+
   ```

2. **Docker & Docker Compose** (for PostgreSQL and Qdrant services)
   ```bash
   docker --version
   docker-compose --version
   ```

3. **Git**
   ```bash
   git --version
   ```

4. **API Keys** (from external services)
   - Telegram Bot Token (from [@BotFather](https://t.me/botfather))
   - OpenAI API Key (from [OpenAI Platform](https://platform.openai.com/account/api-keys))

## Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/law-of-the-game.git
cd law-of-the-game
```

## Step 2: Create Python Virtual Environment

The project includes a pre-configured venv with Python 3.13.9.

**Option A: Use Makefile (Recommended)**
```bash
make install
```

**Option B: Manual Setup**
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

## Step 3: Configure Environment Variables

1. **Copy template file**
   ```bash
   cp .env.example .env.development
   ```

2. **Edit configuration**
   ```bash
   # Open with your editor
   nano .env.development  # or: vim, code, etc.
   ```

3. **Add your API keys**
   ```bash
   # Required
   TELEGRAM_BOT_TOKEN=your_token_from_botfather
   OPENAI_API_KEY=your_api_key_from_openai

   # Optional (defaults shown)
   ENVIRONMENT=development
   LOG_LEVEL=DEBUG

   # Database (auto-configured with Docker)
   DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db

   # Qdrant (auto-configured with Docker)
   QDRANT_HOST=localhost
   QDRANT_PORT=6333
   QDRANT_COLLECTION_NAME=football_documents
   ```

## Step 4: Start Docker Services

PostgreSQL and Qdrant run in Docker containers.

```bash
# Start services in background
make docker-up

# Verify they're running
docker-compose ps

# Check that services are healthy
curl http://localhost:6333/health  # Should return {"status":"ok"}
```

Services status should show:
```
NAME                    STATUS          PORTS
law-of-the-game-db      Up (healthy)    5432->5432/tcp
law-of-the-game-qdrant  Up (healthy)    6333->6333/tcp
```

## Step 5: Run Database Migrations

Initialize the database schema.

```bash
# Apply migrations to PostgreSQL
docker-compose exec postgres psql \
  -U telegram_bot \
  -d telegram_bot_db \
  -f migrations/001_initial_schema.sql

docker-compose exec postgres psql \
  -U telegram_bot \
  -d telegram_bot_db \
  -f migrations/002_add_documents_table.sql

# Verify
docker-compose exec postgres psql \
  -U telegram_bot \
  -d telegram_bot_db \
  -c "\dt"  # List all tables
```

## Step 6: Run Tests

Verify everything is working correctly.

```bash
# Run all tests
make test

# With coverage report
make test-cov

# Open HTML report (macOS)
open htmlcov/index.html

# Expected output
# ============= test session starts ==============
# ... test_database.py ...16 passed...
# ... test_config.py ...10 passed...
# ... test_llm.py ...12 passed...
# ============= 41 passed ==================
```

All tests should pass. If any fail:
1. Check Docker services are running: `docker-compose ps`
2. Review logs: `make docker-logs`
3. Verify API keys in `.env.development`

## Step 7: Run the Bot

```bash
# Terminal 1 - Services already running from Step 4

# Terminal 2 - Run bot
make run-dev

# Expected output
# [INFO] Telegram bot connected
# [INFO] Listening for messages...
```

The bot is now running and will respond to messages on Telegram.

## Step 8: Test the Bot

1. Open Telegram
2. Search for your bot (use the token name from @BotFather)
3. Send a message: "What is a handball in football?"
4. Bot should respond with information about handballs

## Stopping the Bot

```bash
# Terminal 2 - Stop bot
Ctrl+C

# Terminal 1 - Stop services
make docker-down

# Data persists in Docker volumes
# Next time: make docker-up will restore everything
```

## Next Steps

After successful installation:

1. **Understand the Architecture**
   - Read [Architecture Guide](../development/ARCHITECTURE.md)

2. **Explore the Codebase**
   - Review [Files Overview](../development/FILES_OVERVIEW.md)
   - Check source code in `src/`

3. **Daily Development**
   - Follow [Workflow Guide](./WORKFLOW.md)

4. **Upload Documents** (Phase 2)
   - See [QDRANT_PLANNING.md](../vector-search/QDRANT_PLANNING.md)

## Troubleshooting Installation

### Python Version Error
```
Error: Python 3.13+ required, got 3.12
```
**Solution**: Install Python 3.13
```bash
# macOS (using Homebrew)
brew install python@3.13
python3.13 -m venv venv

# Or: Download from https://www.python.org/downloads/
```

### Docker Services Won't Start
```
Error: Cannot connect to Docker daemon
```
**Solution**: Start Docker Desktop
- macOS: Open Applications → Docker
- Linux: `sudo systemctl start docker`
- Windows: Start Docker Desktop application

### Port Already in Use
```
Error: Bind for 0.0.0.0:5432 failed: port is already allocated
```
**Solution**: Another service using the port
```bash
# Find what's using port 5432
lsof -i :5432

# Either stop that service, or:
# Use different port in docker-compose.yml:
# ports:
#   - "5433:5432"  # Host port changed to 5433
```

### Database Connection Error
```
Error: could not translate host name "localhost" to address
```
**Solution**: PostgreSQL not running
```bash
# Check status
docker-compose ps

# Restart
make docker-down
make docker-up

# Wait for health checks to pass (30 seconds)
```

### Tests Failing
```
FAILED test_database.py::test_save_message - Connection refused
```
**Solution**: Ensure Docker services are running
```bash
# Check services
docker-compose ps

# View logs for errors
make docker-logs postgres

# Restart if needed
make docker-down
make docker-up
```

### Missing Environment Variables
```
Error: TELEGRAM_BOT_TOKEN not found in environment
```
**Solution**: Add missing variables to `.env.development`
```bash
# Check what you have
grep TELEGRAM_BOT_TOKEN .env.development

# Add if missing
echo "TELEGRAM_BOT_TOKEN=your_token_here" >> .env.development

# Re-run bot
make run-dev
```

### OpenAI API Error
```
Error: OpenAI API returned error code 401 (Invalid API Key)
```
**Solution**: Check your API key
```bash
# Verify in .env.development
grep OPENAI_API_KEY .env.development

# Should look like: sk-...
# Update if wrong
nano .env.development
```

## Uninstall / Clean Up

To remove everything:

```bash
# Delete virtual environment
rm -rf venv

# Remove Docker containers and volumes (DESTRUCTIVE)
make docker-down
docker-compose down -v

# Remove database file (if using SQLite)
rm conversations.db

# Remove caches
make clean

# Remove test coverage report
rm -rf htmlcov/
```

## Getting Help

If you encounter issues:

1. **Check logs**
   ```bash
   make docker-logs
   make docker-logs-postgres
   make docker-logs-qdrant
   ```

2. **Verify setup**
   ```bash
   # All should pass
   python -c "import telegram; print('Telegram OK')"
   python -c "import openai; print('OpenAI OK')"
   python -c "import sqlalchemy; print('SQLAlchemy OK')"
   python -c "from qdrant_client import QdrantClient; print('Qdrant OK')"
   ```

3. **Run diagnostics**
   ```bash
   # Check system state
   docker-compose ps
   python -m pytest tests/ -v
   make docker-logs | tail -50
   ```

4. **Review documentation**
   - [Docker Setup Guide](../setup/DOCKER_SETUP.md)
   - [Database Design](../development/DATABASE_DESIGN.md)
   - [Quick Start](./QUICK_START.md)

## Security Notes for Production

Before deploying to production:

1. **Change default PostgreSQL password**
   - Edit `docker-compose.yml`
   - Update POSTGRES_PASSWORD
   - Update DATABASE_URL

2. **Use environment-specific .env files**
   ```bash
   # Don't commit secrets!
   echo ".env.production" >> .gitignore
   ```

3. **Secure Telegram token**
   - Never commit to version control
   - Use environment variables or secure storage

4. **Use Qdrant Cloud for production**
   - See [Qdrant Setup](../vector-search/QDRANT_SETUP.md)

## Verification Checklist

After installation, verify:

- [ ] Python 3.13+ installed
- [ ] Docker & Docker Compose running
- [ ] Virtual environment activated
- [ ] All dependencies installed (`pip list` shows required packages)
- [ ] `.env.development` has API keys
- [ ] Docker services healthy (`docker-compose ps`)
- [ ] Migrations applied successfully
- [ ] All tests passing (`make test`)
- [ ] Bot responds to messages on Telegram
- [ ] Logs show no errors (`make docker-logs`)

Once all items are checked, your installation is complete!

## Next: Quick Start

For a 5-minute operational guide, see [Quick Start](./QUICK_START.md).
