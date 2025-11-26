# Quick Start (5 Minutes)

Get the bot running locally in 5 minutes.

## Prerequisites

- Docker Desktop (for services)
- Python 3.13+ (venv is pre-configured)
- Telegram Bot Token from [@BotFather](https://t.me/botfather)

## Setup

### 1. Configure Environment (1 min)

The `.env.development` file is pre-configured. You only need to add your Telegram token:

```bash
# Edit .env.development and replace TELEGRAM_BOT_TOKEN value
# Get token from @BotFather on Telegram
nano .env.development
```

Required variables:
```
TELEGRAM_BOT_TOKEN=your_token_here
OPENAI_API_KEY=your_openai_key_here
```

### 2. Start Services (1 min)

Start PostgreSQL and Qdrant in the background:

```bash
make docker-up
```

You'll see:
```
Services started: PostgreSQL and Qdrant
Verify: curl http://localhost:6333/health
```

Verify Qdrant is responding:
```bash
curl http://localhost:6333/health
# Output: {"status":"ok"}
```

### 3. Run the Bot (1 min)

In a **new terminal**, run the bot:

```bash
make run-dev
```

You'll see:
```
2025-11-24 17:30:00 - INFO - Bot started polling...
```

The bot is now running and ready for messages!

### 4. Test It (1 min)

Open Telegram and send a message to your bot:
```
"What is offside in football?"
```

The bot will respond with an answer based on the Laws of the Game.

### 5. Stop the Bot

When done, stop the bot:
```bash
<Ctrl+C>  # In the bot terminal
```

Stop the services:
```bash
make docker-down
```

Data persists in Docker volumes - next time you run, everything is back!

## Troubleshooting

### Services won't start
```bash
# Check what's running
docker-compose ps

# Check for port conflicts
lsof -i :5432  # PostgreSQL
lsof -i :6333  # Qdrant

# View service logs
make docker-logs
```

### Bot can't connect to services
```bash
# Make sure services are running
docker-compose ps

# Check bot logs for errors
make run-dev  # Error messages will show
```

### "TELEGRAM_BOT_TOKEN is required"
Make sure you added your token to `.env.development`:
```bash
nano .env.development
# Add: TELEGRAM_BOT_TOKEN=your_actual_token_here
```

### Port already in use
If port 6333 (Qdrant) is already in use:
```bash
# Find what's using it
lsof -i :6333

# Kill the process
kill -9 <PID>

# Or restart Docker
docker-compose restart qdrant
```

## Next Steps

- **Development Workflow**: See [WORKFLOW.md](WORKFLOW.md)
- **Detailed Setup**: See [INSTALLATION.md](INSTALLATION.md)
- **Configuration**: See [Environment Setup](../setup/ENVIRONMENTS.md)
- **Architecture**: See [System Design](../development/ARCHITECTURE.md)

## Commands Quick Reference

```bash
# Services
make docker-up              # Start PostgreSQL + Qdrant
make docker-down            # Stop services
make docker-logs            # View logs

# Running
make run-dev                # Run bot
make run-testing            # Test mode
make run-prod               # Production

# Development
make test                   # Run tests
make test-cov               # Tests + coverage
make install                # Install dependencies
make clean                  # Clean up

# Help
make help                   # All available commands
```
