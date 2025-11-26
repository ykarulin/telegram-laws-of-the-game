# Database Design Documentation

## Overview

This project uses **PostgreSQL** for production and **SQLite** for development and testing. The database stores conversation history and document metadata for retrieval-augmented generation (RAG).

## Current Architecture

### Technology Stack

```
Application Layer (src/main.py, src/handlers/)
        ↓
Configuration (src/config.py)
        ↓
Database Layer (src/core/db.py with SQLAlchemy ORM)
        ↓
PostgreSQL (production) OR SQLite (development/testing)
```

### Key Databases

| Database | Use Case | Container |
|----------|----------|-----------|
| **telegram_bot_db** | Production & development conversations | PostgreSQL 16-Alpine |
| **telegram_bot_test** | Unit testing conversations | PostgreSQL 16-Alpine |

## Database Schema

### messages Table

Stores individual messages with proper normalization (one message per record).

**Purpose**: Track conversation history for RAG context retrieval.

```sql
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,                                  -- Auto-increment primary key
    message_id INTEGER NOT NULL,                            -- Telegram message ID
    chat_id INTEGER NOT NULL,                               -- Telegram chat ID
    sender_type VARCHAR(10) NOT NULL,                       -- 'user' or 'bot'
    sender_id VARCHAR(255) NOT NULL,                        -- User ID (numeric) or bot model name
    text TEXT NOT NULL,                                     -- Message content
    reply_to_message_id INTEGER,                            -- For conversation chains
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for performance
    UNIQUE (message_id, chat_id),                           -- Telegram IDs are unique per chat
    INDEX (chat_id, timestamp),                             -- For conversation retrieval
    INDEX (sender_id),                                      -- For user message filtering
    INDEX (reply_to_message_id),                            -- For chain following
    INDEX (sender_type)                                     -- For message type filtering
);
```

**Column Definitions**:

- `id`: Unique database record identifier (auto-increment)
- `message_id`: Telegram's message ID (unique per chat, not globally)
- `chat_id`: Telegram's chat ID (unique identifier for conversation group)
- `sender_type`: Either "user" or "bot" - determines if message is from user or bot
- `sender_id`: User ID as string (supports both numeric Telegram IDs and bot model names like "gpt-5-mini")
- `text`: Full message content (up to Telegram's limit)
- `reply_to_message_id`: References another message ID to build conversation chains
- `timestamp`: When message was created (UTC)

### documents Table

Stores uploaded documents and their Qdrant indexing status.

**Purpose**: Track documents for embeddings and vector database indexing.

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL,                     -- 'laws_of_game', 'competition_rules', etc.
    version VARCHAR(50),                                    -- Document version (e.g., '2024-25')
    content TEXT,                                           -- Full text content
    source_url VARCHAR(512),                                -- Where document was obtained
    uploaded_by VARCHAR(255),                               -- User who uploaded
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,                                         -- Flexible additional data
    qdrant_status VARCHAR(20) DEFAULT 'pending',            -- 'pending', 'indexed', 'failed'
    qdrant_collection_id VARCHAR(255),                      -- Reference to Qdrant collection
    error_message TEXT,                                     -- If indexing failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX (document_type),
    INDEX (uploaded_at),
    INDEX (qdrant_status)
);
```

## Design Decisions

### Why One Message Per Record?

**Decision**: Normalize to one message per database record (not one user+bot pair).

**Rationale**:
1. **Proper normalization**: Violates no normal forms
2. **Multi-chat support**: Single Telegram message ID is only unique per-chat, so composing key with `(message_id, chat_id)` properly handles multiple concurrent conversations
3. **Conversation chains**: Using `reply_to_message_id` to link messages creates natural conversation chains regardless of who sent each message
4. **Sender flexibility**: Can identify both numeric Telegram user IDs and bot model names (strings)

**Schema Example**:
```
User message:  { message_id=1, chat_id=100, sender_type='user',  sender_id='123', text='What is VAR?' }
Bot response:  { message_id=2, chat_id=100, sender_type='bot',   sender_id='gpt-5-mini', text='VAR is...', reply_to_message_id=1 }
```

### Why Composite Key?

Telegram message IDs are unique per-chat, not globally. Using only `message_id` would fail with multiple concurrent users.

**Solution**: Unique constraint on `(message_id, chat_id)` pair.

This enables:
- Unlimited concurrent users
- Multiple chats with same user
- Proper message isolation per conversation

### Why sender_id as String?

Bot responses use model name (e.g., "gpt-5-mini") as sender_id. User messages use numeric user IDs converted to strings for consistency.

**Benefit**: Single type for all sender identifiers, no type conversions needed.

## Database Configuration

### Environment Variables

**Development (.env.development)**:
```bash
DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db
ENVIRONMENT=development
```

**Testing (.env.testing)**:
```bash
DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_test
ENVIRONMENT=testing
```

**Production (.env.production)**:
```bash
DATABASE_URL=postgresql://username:password@prod-host:5432/telegram_bot_db
ENVIRONMENT=production
```

## Migrations

### Migration Files

**migrations/001_initial_schema.sql** - Creates messages table with all indexes

**migrations/002_add_documents_table.sql** - Adds documents table for Qdrant integration

### Running Migrations

**Docker (PostgreSQL in Docker)**:
```bash
# Start PostgreSQL
make docker-up

# Apply migrations
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db -f migrations/001_initial_schema.sql
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db -f migrations/002_add_documents_table.sql
```

**Direct PostgreSQL**:
```bash
psql -h localhost -U telegram_bot -d telegram_bot_db -f migrations/001_initial_schema.sql
psql -h localhost -U telegram_bot -d telegram_bot_db -f migrations/002_add_documents_table.sql
```

## Python Database Layer

### Core Classes

**src/core/db.py**

```python
@dataclass
class Message:
    """Represents a single message in database."""
    message_id: int
    chat_id: int
    sender_type: str              # 'user' or 'bot'
    sender_id: str                # User ID or bot model name
    text: str
    reply_to_message_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    db_id: Optional[int] = None

class ConversationDatabase:
    """SQLAlchemy-based database layer."""

    def save_message(message: Message) -> bool:
        """Save a single message to database."""

    def get_message(message_id: int, chat_id: int) -> Optional[Message]:
        """Retrieve a specific message."""

    def get_conversation_chain(chat_id: int, start_message_id: int, user_id: str) -> List[Message]:
        """Get conversation chain from specific message, stopping at different user."""

    def get_latest_messages(chat_id: int, user_id: str, limit: int = 10) -> List[Message]:
        """Get most recent messages for context."""
```

### Conversation Retrieval Logic

When user sends a reply:

1. Get the replied-to message ID from Telegram
2. Load that message from database
3. Follow `reply_to_message_id` chain backwards
4. **Stop when**:
   - Message not found (broken chain)
   - Different user sent the message (multi-user conversation)
5. Return messages in chronological order for LLM context

**Example Chain**:
```
Message 1: User asks "What is VAR?" (sender_id='123')
Message 2: Bot responds (sender_id='gpt-5-mini', reply_to=1)
Message 3: User follows up "How does it work?" (sender_id='123', reply_to=2)

get_conversation_chain(chat_id=100, start_message_id=3, user_id='123')
→ Returns: [Message 1, Message 2, Message 3]

If different user replies to message 3:
Message 4: Different user (sender_id='456', reply_to=3)

get_conversation_chain(chat_id=100, start_message_id=4, user_id='456')
→ Returns: [Message 4] (stops at message 3 boundary)
```

## Data Persistence

### SQLite (Development)

- File: `conversations.db` (local disk)
- Auto-created on first run
- Sufficient for single-user testing
- Simple backup: `cp conversations.db conversations.db.backup`

### PostgreSQL (Production)

- Container: `law-of-the-game-db` (Docker)
- Volume: `postgres_data` (persistent Docker volume)
- Data survives container restart
- Backup: `docker-compose exec postgres pg_dump ...`

## Common Database Tasks

### Check Database Status

```bash
# PostgreSQL in Docker
docker-compose ps

# Database size
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT pg_size_pretty(pg_database_size('telegram_bot_db'));"

# Message count
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"
```

### Backup Data

```bash
# PostgreSQL
docker-compose exec -T postgres pg_dump -U telegram_bot telegram_bot_db > backup.sql

# Restore
docker-compose exec -T postgres psql -U telegram_bot telegram_bot_db < backup.sql
```

### Run Tests

```bash
# All tests use .env.testing with test database
make test

# With coverage
make test-cov

# Specific test file
pytest tests/test_database.py -v
```

## Performance Considerations

### Indexes

Created indexes on:
- `(chat_id, timestamp)` - For retrieving conversation history
- `sender_id` - For filtering user messages
- `reply_to_message_id` - For chain traversal
- `message_id, chat_id` - For message lookup

These optimize the common queries:
- "Get conversation history for chat X"
- "Get latest messages from user Y"
- "Follow reply chain backwards"

### Query Examples

```python
# Efficient: Uses index on (chat_id, timestamp)
db.get_latest_messages(chat_id=100, user_id='123', limit=10)

# Efficient: Uses index on (message_id, chat_id)
db.get_message(message_id=5, chat_id=100)

# Efficient: Uses indexes on chat_id, reply_to_message_id
db.get_conversation_chain(chat_id=100, start_message_id=5, user_id='123')
```

## Troubleshooting

### Database Connection Errors

**Error**: `"could not connect to server"`

**Solution**:
```bash
# Check PostgreSQL is running
docker-compose ps

# Check logs
docker-compose logs postgres

# Verify connection settings in .env
# DATABASE_URL=postgresql://telegram_bot:telegram_bot_password@localhost:5432/telegram_bot_db
```

### Migration Errors

**Error**: `"relation 'messages' already exists"`

**Solution**: Migrations are idempotent. This is safe to ignore if table exists.

### Data Not Saving

**Solution**:
```bash
# Verify messages are saved
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db -c "SELECT COUNT(*) FROM messages;"

# Check for permission errors
docker-compose logs postgres | grep -i error

# Test database connection
pytest tests/test_database.py -v
```

## Next Steps

- [Phase 2: Document Management Services](../../QDRANT_PLANNING.md#phase-2-document-management-services)
- [Vector Database Setup](../vector-search/QDRANT_SETUP.md)
- [Production Deployment](../deployment/DEPLOYMENT.md)

## References

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
