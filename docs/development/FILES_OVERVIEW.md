# Project Files Overview

Complete guide to the project structure, file organization, and dependencies.

## Directory Structure

```
law-of-the-game/
├── README.md                           # Main project overview
│
├── Configuration & Environment
├── .env.example                        # Template for environment variables
├── .env.development                    # Development configuration
├── .env.testing                        # Testing configuration
├── .env.production                     # Production template
│
├── src/                                # Application source code
│   ├── __init__.py
│   ├── main.py                         # Bot entry point (async Telegram handler)
│   ├── config.py                       # Configuration management
│   │
│   ├── core/                           # Core infrastructure
│   │   ├── db.py                       # SQLAlchemy database layer
│   │   ├── vector_db.py                # Qdrant vector database client
│   │   ├── conversation.py             # Conversation context management
│   │   └── llm.py                      # OpenAI integration
│   │
│   ├── services/                       # Business logic services
│   │   ├── message_handler.py          # Telegram message processing
│   │   ├── embedding_service.py        # Document embedding (future)
│   │   ├── document_service.py         # Document management (future)
│   │   ├── retrieval_service.py        # Vector search (future)
│   │   └── pdf_parser.py               # PDF text extraction
│   │
│   ├── handlers/                       # Telegram event handlers
│   │   ├── message_handler.py          # Message event routing
│   │   └── error_handler.py            # Error handling (future)
│   │
│   └── cli/                            # Command-line interface (future)
│       └── __init__.py
│
├── tests/                              # Test suite (pytest)
│   ├── __init__.py
│   ├── test_database.py                # Database tests (16 tests)
│   ├── test_config.py                  # Configuration tests
│   ├── test_llm.py                     # LLM integration tests
│   └── test_bot.py                     # Bot handler tests
│
├── migrations/                         # Database schema migrations
│   ├── 001_initial_schema.sql          # Messages table schema
│   └── 002_add_documents_table.sql     # Documents table schema
│
├── docs/                               # Documentation
│   ├── getting-started/                # Getting started guides
│   │   ├── QUICK_START.md              # 5-minute setup
│   │   └── WORKFLOW.md                 # Development workflow
│   │
│   ├── setup/                          # Setup & configuration
│   │   ├── DOCKER_SETUP.md             # Docker & docker-compose guide
│   │   ├── DATABASE_SETUP.md           # PostgreSQL setup
│   │   ├── POSTGRES_SETUP.md           # Quick PostgreSQL start
│   │   ├── POSTGRES_MIGRATION.md       # SQLite → PostgreSQL migration
│   │   └── ENVIRONMENTS.md             # Environment configuration
│   │
│   ├── development/                    # Developer documentation
│   │   ├── DATABASE_DESIGN.md          # Database schema & design
│   │   ├── FILES_OVERVIEW.md           # This file
│   │   ├── ARCHITECTURE.md             # System architecture (future)
│   │   └── INSTALLATION.md             # Detailed installation (future)
│   │
│   ├── vector-search/                  # Vector database guides
│   │   ├── QDRANT_PLANNING.md          # Implementation planning
│   │   └── QDRANT_SETUP.md             # Qdrant server setup
│   │
│   ├── deployment/                     # Production deployment
│   │   └── DEPLOYMENT.md               # VPS deployment guide
│   │
│   └── archive/                        # Obsolete documentation
│       ├── PYTHON_314_NOTES.md         # Python 3.14 compatibility notes
│       └── POSTGRES_IMPLEMENTATION_SUMMARY.md  # Old summary
│
├── Makefile                            # Build automation
├── docker-compose.yml                  # PostgreSQL & Qdrant services
├── pytest.ini                          # Pytest configuration
├── requirements.txt                    # Python dependencies
└── .gitignore                          # Git ignore rules
```

## Core Application Files

### src/main.py
- **Size**: ~100 lines
- **Purpose**: Telegram bot entry point
- **Responsibility**: Initialize bot, connect to Telegram API, start polling for messages
- **Key Imports**: `AsyncApplication`, `.config`, `.handlers`
- **Dependencies**: python-telegram-bot, config module

### src/config.py
- **Size**: ~150 lines
- **Purpose**: Configuration management
- **Responsibility**: Load environment variables, validate settings, provide config to all modules
- **Key Classes**: `Config` (dataclass), `Environment` (enum)
- **Supports**: Multiple environments (development, testing, production)
- **New Fields**: Qdrant settings (host, port, API key, collection name, etc.)

### src/core/db.py
- **Size**: ~220 lines
- **Purpose**: Database persistence layer using SQLAlchemy ORM
- **Responsibility**: Message CRUD, conversation chain retrieval, multi-chat isolation
- **Key Classes**:
  - `MessageModel`: SQLAlchemy model mapping to messages table
  - `Message`: Dataclass for application layer
  - `ConversationDatabase`: Main database interface
- **Key Methods**:
  - `save_message()`: Persist message (one record per message)
  - `get_message()`: Retrieve by message_id + chat_id
  - `get_conversation_chain()`: Follow reply_to chain
  - `get_latest_messages()`: Recent messages for context
- **Database**: PostgreSQL (production) or SQLite (testing)

### src/core/vector_db.py
- **Size**: ~220 lines
- **Purpose**: Qdrant vector database client
- **Responsibility**: Connect to Qdrant server, manage collections, perform semantic search
- **Key Classes**:
  - `VectorDatabase`: Main Qdrant interface
  - `RetrievedChunk`: Search result with score and metadata
- **Key Methods**:
  - `create_collection()`: Create vector collection
  - `upsert_points()`: Add/update vector points
  - `search()`: Semantic search with similarity threshold
  - `health_check()`: Verify server is running
- **Dependencies**: qdrant-client library

### src/core/llm.py
- **Size**: ~130 lines
- **Purpose**: OpenAI API integration
- **Responsibility**: Generate responses using ChatGPT, handle conversation context, manage tokens
- **Key Features**:
  - System prompt with football rules expertise
  - Conversation context injection
  - Response truncation for Telegram limits
  - Token counting
  - Error handling with retry logic
- **Dependencies**: openai library

### src/services/message_handler.py
- **Size**: ~100 lines
- **Purpose**: Orchestrate message processing
- **Responsibility**: Save user message, retrieve context, generate response, save bot response
- **Key Method**: `handle_message()` - Main message pipeline
- **Database Interactions**:
  1. Save user message
  2. Get conversation chain
  3. Generate LLM response
  4. Save bot response with reply_to_message_id
- **New Feature**: Saves two records (user + bot) instead of combining them

### src/services/pdf_parser.py
- **Size**: ~200 lines
- **Purpose**: PDF text extraction
- **Responsibility**: Parse PDFs, extract text and tables, validate files
- **Key Methods**:
  - `validate_file()`: Check size and format
  - `extract_text()`: Get all text with optional layout preservation
  - `extract_tables()`: Extract structured table data
  - `get_pdf_info()`: Metadata (pages, author, etc.)
- **Dependencies**: pdfplumber library
- **Features**: Error recovery, page-by-page processing, layout preservation

## Configuration Files

### .env.development / .env.testing / .env.production
- **Purpose**: Environment-specific settings
- **Contents**:
  - Telegram bot token
  - OpenAI API key & model
  - Database connection string
  - Qdrant settings (host, port, API key, collection name)
  - Embedding configuration (batch size, TOP_K, similarity threshold)
  - Log level (DEBUG/INFO/WARNING)

### docker-compose.yml
- **Services**:
  - **postgres**: PostgreSQL 16-Alpine container
    - Port: 5432
    - Credentials: telegram_bot / telegram_bot_password
    - Database: telegram_bot_db
    - Volume: postgres_data (persistent storage)
  - **qdrant**: Qdrant vector database container
    - Ports: 6333 (gRPC), 6334 (HTTP)
    - Volume: qdrant_data (persistent storage)
    - Healthcheck: curl to /health endpoint
- **Volumes**: postgres_data, qdrant_data (Docker-managed persistent storage)

### Makefile
- **Commands**:
  - `make install` - Create venv and install dependencies
  - `make test` - Run all tests
  - `make test-cov` - Run tests with coverage report
  - `make run-dev` - Run bot in development
  - `make run-testing` - Run bot in test mode
  - `make run-prod` - Run bot in production
  - `make docker-up` - Start PostgreSQL & Qdrant
  - `make docker-down` - Stop services (data persists)
  - `make docker-logs` - View all service logs
  - `make clean` - Remove caches and temp files

### requirements.txt
- **Core**:
  - python-telegram-bot==21.8 (Telegram API)
  - openai==2.8.1 (OpenAI ChatGPT)
  - python-dotenv==1.0.0 (Environment loading)
  - sqlalchemy==2.0.23 (ORM)
  - psycopg==3.1.14 (PostgreSQL driver)
- **Vector DB**:
  - qdrant-client==1.16.0 (Qdrant client)
  - pdfplumber==0.10.4 (PDF parsing)
- **Testing**:
  - pytest==7.4.3 (Test framework)
  - pytest-asyncio==0.23.2 (Async test support)
  - pytest-cov==4.1.0 (Coverage reporting)

## Database Files

### migrations/001_initial_schema.sql
- **Purpose**: PostgreSQL schema for messages table
- **Creates**: messages table with proper indexes
- **Columns**: message_id, chat_id, sender_type, sender_id, text, reply_to_message_id, timestamp
- **Constraints**: UNIQUE (message_id, chat_id) - Telegram ID uniqueness per chat

### migrations/002_add_documents_table.sql
- **Purpose**: PostgreSQL schema for documents table
- **Creates**: documents table for uploaded file tracking
- **Columns**: name, document_type, version, content, source_url, metadata, qdrant_status, etc.
- **For**: Document management and Qdrant indexing status tracking

## Test Files

### tests/test_database.py (16 tests)
- **MessageStorage Tests** (6):
  - Save and retrieve user/bot messages
  - Handle replies and reply chains
  - Non-existent message handling
- **ConversationChains Tests** (5):
  - Build linear conversation chains
  - Handle branched conversations
  - Stop at broken chains and user boundaries
- **LatestMessages Tests** (3):
  - Empty chat handling
  - Limit parameter
  - Chat isolation
- **Integration Tests** (2):
  - Realistic conversation flows
  - Multi-user isolated conversations

**Coverage**: 100% of database layer

### tests/test_config.py
- Configuration loading from environment
- Multi-environment support
- Missing required fields

### tests/test_llm.py
- OpenAI API integration
- Conversation context handling
- Response truncation
- Error handling

### tests/test_bot.py
- Message handler integration
- Typing indicator functionality
- Error handling and user feedback

## Documentation Files

### docs/getting-started/QUICK_START.md
- 5-minute setup guide
- Prerequisites and basic steps
- Verification and troubleshooting

### docs/getting-started/WORKFLOW.md
- Daily development workflow
- Common tasks
- Debugging techniques

### docs/setup/DOCKER_SETUP.md
- Docker & docker-compose overview
- Service configuration
- Data persistence explanation
- Common tasks and troubleshooting

### docs/setup/DATABASE_SETUP.md
- SQLite vs PostgreSQL comparison
- Setup instructions for both
- Schema documentation
- Migration guide
- Backup/restore procedures

### docs/development/DATABASE_DESIGN.md
- Database schema details
- Design decisions and rationale
- Conversation chain logic
- Configuration and migrations
- Performance tuning

### docs/vector-search/QDRANT_SETUP.md
- Qdrant vector database setup
- 5 different setup options
- Configuration details
- Monitoring and performance tuning

### docs/vector-search/QDRANT_PLANNING.md
- Complete Phase 1-6 implementation plan
- Architecture decisions
- Document format analysis
- Cost analysis (~$0.05-0.10/month)
- 22 specific implementation tasks

## File Dependencies

```
main.py
  ├── imports: config, AsyncApplication
  ├── imports: handlers.message_handler
  └── calls: config.load_config()

config.py
  ├── defines: Config dataclass, Environment enum
  └── provides: Configuration to all modules

handlers/message_handler.py
  ├── uses: ConversationDatabase
  ├── uses: LLMClient
  └── calls: save_message(), get_conversation_chain()

core/db.py
  ├── uses: SQLAlchemy ORM
  ├── models: messages, documents tables
  └── supports: PostgreSQL, SQLite

core/vector_db.py
  ├── uses: qdrant-client library
  ├── connects: Qdrant server on localhost:6333
  └── manages: Collections, points, search

services/pdf_parser.py
  ├── uses: pdfplumber library
  └── extracts: Text, tables, metadata

tests/test_*.py
  ├── imports: pytest, unittest.mock
  ├── tests: All major modules
  └── database: Uses .env.testing configuration
```

## Development Statistics

### Code Size
```
src/main.py              ~100 lines
src/config.py            ~150 lines
src/core/db.py           ~220 lines
src/core/vector_db.py    ~220 lines
src/core/llm.py          ~130 lines
src/services/           ~300 lines (total)
────────────────────────────────
Total Application        ~1,120 lines
```

### Test Coverage
```
test_database.py         16 tests
test_config.py           ~10 tests
test_llm.py              ~12 tests
test_bot.py              ~3 tests
────────────────────────────────
Total Tests              ~41 tests
Coverage                 ~90%
```

### Documentation
```
QUICK_START.md           ~150 lines
WORKFLOW.md              ~200 lines
DOCKER_SETUP.md          ~400 lines
DATABASE_DESIGN.md       ~350 lines
QDRANT_SETUP.md          ~450 lines
QDRANT_PLANNING.md       ~550 lines
DEPLOYMENT.md            ~450 lines
────────────────────────────────
Total Documentation      ~2,550 lines
```

## Next Steps

For different paths:

- **Just Starting?** → [QUICK_START.md](../getting-started/QUICK_START.md)
- **Understanding Architecture?** → [DATABASE_DESIGN.md](DATABASE_DESIGN.md)
- **Setting Up Services?** → [DOCKER_SETUP.md](../setup/DOCKER_SETUP.md)
- **Planning Qdrant?** → [QDRANT_PLANNING.md](../vector-search/QDRANT_PLANNING.md)
- **Deploying to Production?** → [DEPLOYMENT.md](../deployment/DEPLOYMENT.md)
