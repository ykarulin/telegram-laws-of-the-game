# Multi-Environment Configuration

This project supports three environments: **development**, **testing**, and **production**.

## Environment Files

Each environment has its own configuration file:

- `.env.development` - Local development with verbose logging
- `.env.testing` - Testing bot for QA purposes
- `.env.production` - Production bot with minimal logging

### Creating Environment Files

1. Copy `.env.example` to create environment-specific files:
   ```bash
   cp .env.example .env.development
   cp .env.example .env.testing
   cp .env.example .env.production
   ```

2. Update each file with the appropriate bot token:
   ```bash
   # For testing environment
   ENVIRONMENT=testing
   TELEGRAM_BOT_TOKEN=<your_testing_bot_token_here>
   LOG_LEVEL=INFO
   ```

## Running Locally

### Development
```bash
# Using make
make run-dev

# Or manually
ENVIRONMENT=development python main.py

# Or by loading .env.development first
source venv/bin/activate && python main.py
# (expects .env.development to be loaded)
```

### Testing Bot
```bash
make run-testing
```

### Production Bot (locally)
```bash
make run-prod
```

## Docker Deployment

### Development Container
```bash
make docker-up
# Or explicitly:
docker-compose --profile dev up -d
```

View logs:
```bash
docker-compose logs -f bot-dev
```

### Testing Container
```bash
make docker-up-testing
docker-compose logs -f bot-testing
```

### Production Container
```bash
make docker-up-prod
docker-compose logs -f bot-prod
```

### Stop All Containers
```bash
make docker-down
```

## Configuration Options

The `Config` class supports these environment variables:

| Variable | Options | Default | Description |
|----------|---------|---------|-------------|
| `ENVIRONMENT` | development, testing, production | development | Deployment environment |
| `TELEGRAM_BOT_TOKEN` | string | (required) | Bot token from @BotFather |
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL | INFO | Logging verbosity |

### Debug Mode

- **Development**: `debug=True` (more verbose logging)
- **Testing**: `debug=True` (more verbose logging)
- **Production**: `debug=False` (minimal logging)

## Best Practices

1. **Never commit actual bot tokens** - Use `.env*` in `.gitignore`
2. **Keep `.env.example` updated** - Reflect all available config options
3. **Test environment-specific behavior** - Verify each environment works independently
4. **Use different bot tokens** - Create separate bots in @BotFather for each environment
5. **Production isolation** - Use dedicated hosting/VPS for production bot

## Docker Compose Profiles

Docker Compose uses [profiles](https://docs.docker.com/compose/profiles/) to manage services:

```bash
# Run only development
docker-compose --profile dev up

# Run only testing
docker-compose --profile testing up

# Run only production
docker-compose --profile prod up

# Run multiple profiles
docker-compose --profile dev --profile testing up

# View all services (regardless of profile)
docker-compose config
```

## Testing Configuration

Tests use mocking and don't require real bot tokens. The configuration system is tested in `tests/test_config.py`.

Run tests:
```bash
make test
```

## Environment Variables Priority

The `load_config()` function loads variables in this order:

1. `.env.{ENVIRONMENT}` file (if exists)
2. `.env` file (fallback)
3. System environment variables (override)

Example: If `ENVIRONMENT=testing` is set, the loader tries `.env.testing` first, then falls back to `.env`.
