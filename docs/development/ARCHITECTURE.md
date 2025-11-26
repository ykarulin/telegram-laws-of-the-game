# System Architecture

Comprehensive documentation of the Football Rules Bot system design and component interactions.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Telegram User                         │
│              (sends messages, receives replies)          │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ↓ (Telegram Bot API)
┌──────────────────────────────────────────────────────────┐
│                  Python Application Layer                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  main.py    │→ │ handlers/    │→ │ services/    │   │
│  │ (async bot) │  │message_      │  │message_      │   │
│  │             │  │handler.py    │  │handler.py    │   │
│  └─────────────┘  └──────────────┘  └──────────────┘   │
│         ↑                     ↓              ↓            │
│  ┌──────────────────────────────────────────────────┐   │
│  │         core/ (Infrastructure Layer)            │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │   │
│  │  │config.py │  │ db.py    │  │ vector_db.py │  │   │
│  │  │(settings)│  │(database)│  │(search)      │  │   │
│  │  └──────────┘  └──────────┘  └──────────────┘  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │   │
│  │  │ llm.py   │  │pdf_parser│  │conversation  │  │   │
│  │  │(OpenAI)  │  │.py       │  │.py           │  │   │
│  │  └──────────┘  └──────────┘  └──────────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
       ↓              ↓                    ↓
┌──────────────┐ ┌──────────────┐ ┌────────────────┐
│ PostgreSQL   │ │ Qdrant       │ │ OpenAI Cloud   │
│ (persistent  │ │ (vectors)    │ │ (ChatGPT API)  │
│  storage)    │ │              │ │                │
│              │ │              │ │                │
│ • Messages   │ │ • Chunks     │ │ • LLM API      │
│ • Documents  │ │ • Embeddings │ │ • Models       │
│ • Context    │ │ • Search idx │ │ • Responses    │
└──────────────┘ └──────────────┘ └────────────────┘
```

## Component Layers

### 1. Application Layer (src/)

**Responsibility**: Orchestrate user interactions and business logic.

#### main.py
- **Purpose**: Telegram bot entry point
- **Responsibility**:
  - Initialize async Telegram bot
  - Connect to Telegram Bot API
  - Setup message handlers
  - Start polling for updates
- **Key Classes**:
  - `Application`: python-telegram-bot async application
- **Dependencies**: AsyncApplication, handlers

#### handlers/message_handler.py
- **Purpose**: Route Telegram events
- **Responsibility**: Dispatch messages to service handlers
- **Key Methods**:
  - `handle_message()`: Process incoming messages
  - `handle_error()`: Handle exceptions
- **Uses**: ConversationDatabase, LLMClient, PDFParser

### 2. Infrastructure Layer (src/core/)

**Responsibility**: Provide abstraction over external services.

#### config.py
- **Purpose**: Configuration management
- **Responsibility**:
  - Load environment variables
  - Validate settings
  - Provide Config dataclass
- **Scope**: Application-wide settings (database, APIs, logging)
- **Supports**: Multiple environments (development, testing, production)
- **Key Configuration**:
  - Database connection string
  - API keys (Telegram, OpenAI, Qdrant)
  - Qdrant settings (host, port, collection name)
  - Embedding configuration (model, batch size, threshold)
  - Logging level

#### db.py (Database Layer)
- **Purpose**: Message persistence and conversation retrieval
- **Responsibility**:
  - Save individual messages (one record per message)
  - Retrieve conversation chains
  - Isolate messages by chat and user
  - Manage message relationships (reply_to chains)
- **Key Classes**:
  - `MessageModel`: SQLAlchemy ORM model for messages table
  - `DocumentModel`: SQLAlchemy ORM model for documents table
  - `Message`: Dataclass for application layer
  - `ConversationDatabase`: Main database interface
- **Database**: PostgreSQL (production) or SQLite (testing)
- **Schema**:
  - `messages`: One record per message
  - `documents`: Track uploaded documents and Qdrant indexing status
- **Key Methods**:
  ```python
  save_message(message: Message) -> bool
  get_message(message_id: int, chat_id: int) -> Optional[Message]
  get_conversation_chain(chat_id: int, start_message_id: int, user_id: str) -> List[Message]
  get_latest_messages(chat_id: int, user_id: str, limit: int = 10) -> List[Message]
  ```

#### vector_db.py (Vector Database Client)
- **Purpose**: Interface with Qdrant vector database
- **Responsibility**:
  - Connect to Qdrant server
  - Manage collections (create, delete)
  - Store and update vector points
  - Perform semantic search
  - Health checks
- **Key Classes**:
  - `VectorDatabase`: Qdrant client wrapper
  - `RetrievedChunk`: Search result with score and metadata
- **Key Methods**:
  ```python
  create_collection(collection_name: str, vector_size: int) -> bool
  upsert_points(collection_name: str, points: List[PointStruct]) -> bool
  search(collection_name: str, query_vector: List[float], limit: int, min_score: float) -> List[RetrievedChunk]
  delete_collection(collection_name: str) -> bool
  health_check() -> bool
  ```
- **Qdrant Settings**:
  - Host: localhost:6333 (development) or cloud URL (production)
  - Collection: football_documents (or similar)
  - Vector size: 512 dimensions (text-embedding-3-small)
  - Distance metric: COSINE similarity (0.0-1.0)

#### llm.py (LLM Integration)
- **Purpose**: OpenAI API integration
- **Responsibility**:
  - Generate responses to user questions
  - Handle conversation context
  - Manage token limits
  - Implement retry logic
  - Format responses for Telegram
- **Key Classes**:
  - `LLMClient`: OpenAI wrapper
- **Key Methods**:
  ```python
  generate_response(user_message: str, conversation_context: List[str]) -> str
  get_system_prompt() -> str
  count_tokens(text: str) -> int
  ```
- **Configuration**:
  - Model: gpt-3.5-turbo or gpt-4
  - Temperature: 1.0 (controlled randomness)
  - Max tokens: 2000 (within Telegram limits)
  - Timeout: 30 seconds
- **Features**:
  - Token counting (estimates response length)
  - Response truncation (respects Telegram's 4096 char limit)
  - Fallback parameters (max_tokens → max_completion_tokens)
  - Retry on rate limits

#### conversation.py (Context Management)
- **Purpose**: Build conversation context for LLM
- **Responsibility**:
  - Retrieve conversation chain from database
  - Format messages as LLM context
  - Manage context window size
  - Handle multi-turn conversations
- **Key Classes**:
  - `ConversationManager`: Context builder
- **Key Methods**:
  ```python
  build_context(chat_id: int, user_id: str, message_id: int) -> List[str]
  format_for_llm(messages: List[Message]) -> str
  ```

### 3. Service Layer (src/services/)

**Responsibility**: Business logic and specialized operations.

#### message_handler.py (Message Pipeline)
- **Purpose**: Orchestrate message handling
- **Workflow**:
  1. Receive user message from Telegram
  2. Save user message to database
  3. Retrieve conversation chain for context
  4. Generate response using LLM + context
  5. Save bot response to database
  6. Send response back to Telegram
- **Error Handling**:
  - Database errors → Log and notify user
  - LLM errors → Retry or send fallback message
  - Telegram errors → Log and continue
- **Key Method**: `handle_message(update, context)`

#### pdf_parser.py (Document Processing)
- **Purpose**: Extract text from PDF documents
- **Responsibility**:
  - Parse PDF files
  - Extract text while preserving structure
  - Extract tables
  - Get document metadata
  - Validate file format and size
- **Key Classes**:
  - `PDFParser`: PDF extraction engine
- **Key Methods**:
  ```python
  validate_file(file_path: str) -> bool
  extract_text(file_path: str, preserve_layout: bool) -> str
  extract_tables(file_path: str) -> List[List[List[str]]]
  extract_text_and_tables(file_path: str) -> Dict[str, Any]
  get_pdf_info(file_path: str) -> Dict[str, Any]
  ```
- **Library**: pdfplumber (robust PDF handling)
- **Features**:
  - Layout-aware extraction (preserves multi-column structure)
  - Table extraction and formatting
  - Page-by-page processing with error recovery
  - Metadata extraction (title, author, creation date)
  - File validation (max 100 MB)

#### embedding_service.py (Phase 2)
- **Purpose**: Convert documents to embeddings
- **Responsibility**:
  - Chunk documents into semantic units
  - Call OpenAI embedding API
  - Manage embedding batch size
  - Handle retry and rate limiting
- **Workflow**:
  1. Load document
  2. Split into chunks (preserving context)
  3. Embed chunks using text-embedding-3-small
  4. Store embeddings in Qdrant
  5. Update documents table status

#### document_service.py (Phase 2)
- **Purpose**: Manage document lifecycle
- **Responsibility**:
  - Save documents to database
  - Track Qdrant indexing status
  - Update document metadata
  - Delete documents and related vectors
  - Query document repository

#### retrieval_service.py (Phase 2)
- **Purpose**: Retrieve and format context
- **Responsibility**:
  - Convert user query to embedding
  - Search Qdrant for similar chunks
  - Filter by relevance threshold
  - Format retrieved chunks as context
  - Handle source attribution

## Data Flow

### Message Flow (Current - Phase 1)

```
User Message in Telegram
        ↓
Telegram Bot API → handlers/message_handler.py
        ↓
src/services/message_handler.py.handle_message()
        ↓
┌─ Save User Message ─────────────────────┐
│ ConversationDatabase.save_message()     │
│ → Stored in PostgreSQL messages table   │
└─────────────────────────────────────────┘
        ↓
┌─ Get Conversation Context ──────────────┐
│ ConversationManager.build_context()     │
│ → Retrieve via get_conversation_chain() │
│ → Format as LLM input                   │
└─────────────────────────────────────────┘
        ↓
┌─ Generate Response ─────────────────────┐
│ LLMClient.generate_response()           │
│ → Call OpenAI API (gpt-3.5-turbo)       │
│ → Use conversation context              │
│ → Truncate to Telegram limits (4096)    │
└─────────────────────────────────────────┘
        ↓
┌─ Save Bot Response ─────────────────────┐
│ ConversationDatabase.save_message()     │
│ → Stored with reply_to_message_id       │
│ → sender_type='bot'                     │
│ → sender_id=model name                  │
└─────────────────────────────────────────┘
        ↓
Send Response to Telegram
        ↓
User Receives Reply
```

### Conversation Chain Retrieval

When user replies to a message:

```
Telegram update.message.reply_to_message.message_id
        ↓
ConversationManager.get_conversation_chain()
        ↓
Fetch message from DB → Load replied-to message
        ↓
Follow reply_to_message_id chain backwards
        ↓
┌─ Stop conditions ────┐
│ • Message not found  │
│ • Different user     │
│ • No more replies    │
└─────────────────────┘
        ↓
Return messages in chronological order
        ↓
Format as conversation context
        ↓
Send to LLM
```

### Future Flow (Phase 2+)

```
User Message
        ↓
Current flow (Message 1-5 above)
        ↓
Before generating response: [NEW]
        ├─ Convert message to embedding (text-embedding-3-small)
        ├─ Search Qdrant for relevant document chunks
        │  └─ Similarity score > threshold
        ├─ Format chunks as "Retrieved context:" section
        └─ Append to conversation context
        ↓
LLM generates response with document grounding
        ↓
Response sent to user
```

## Database Schema

### messages Table

```sql
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL,                           -- Telegram ID
    chat_id INTEGER NOT NULL,                              -- Telegram chat
    sender_type VARCHAR(10) NOT NULL,                      -- 'user' or 'bot'
    sender_id VARCHAR(255) NOT NULL,                       -- User ID or bot model
    text TEXT NOT NULL,                                    -- Message content
    reply_to_message_id INTEGER,                           -- For chains
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (message_id, chat_id),
    INDEX (chat_id, timestamp),
    INDEX (sender_id),
    INDEX (reply_to_message_id)
);
```

**Key Design Decision**: One message = one record
- Enables proper normalization
- Supports conversation chains via reply_to_message_id
- Handles multi-chat isolation with (message_id, chat_id) composite key
- Allows both numeric user IDs and string bot model names in sender_id

### documents Table

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL,                    -- 'laws_of_game', etc.
    version VARCHAR(50),
    content TEXT,
    source_url VARCHAR(512),
    uploaded_by VARCHAR(255),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    qdrant_status VARCHAR(20) DEFAULT 'pending',           -- 'pending', 'indexed', 'failed'
    qdrant_collection_id VARCHAR(255),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX (document_type),
    INDEX (qdrant_status)
);
```

## Configuration Management

### Configuration Hierarchy

```
System Environment
        ↓
.env.{ENVIRONMENT} file (e.g., .env.development)
        ↓
src/config.py loads and validates
        ↓
Config dataclass instance
        ↓
All modules use Config object
```

### Environment Variables

**Core Settings**:
- `ENVIRONMENT`: development, testing, production
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR
- `TELEGRAM_BOT_TOKEN`: Telegram Bot API token

**Database**:
- `DATABASE_URL`: PostgreSQL connection string

**Vector Database**:
- `QDRANT_HOST`: Server hostname
- `QDRANT_PORT`: Server port (usually 6333)
- `QDRANT_API_KEY`: API key if authentication required
- `QDRANT_COLLECTION_NAME`: Collection name (e.g., "football_documents")

**LLM & Embeddings**:
- `OPENAI_API_KEY`: OpenAI API key
- `OPENAI_MODEL`: Model name (e.g., "gpt-3.5-turbo")
- `EMBEDDING_MODEL`: Embedding model (e.g., "text-embedding-3-small")
- `EMBEDDING_BATCH_SIZE`: Chunks per embedding request
- `TOP_K_RETRIEVALS`: Number of search results
- `SIMILARITY_THRESHOLD`: Minimum relevance score

## Deployment Architecture

### Development Setup

```
Developer's Computer
├─ Python 3.13 venv
├─ PostgreSQL (Docker)
├─ Qdrant (Docker)
└─ Python bot (local)
```

### Production Setup

```
VPS / Cloud Server
├─ Python 3.13 (system-wide)
├─ PostgreSQL (Docker or managed service)
├─ Qdrant Cloud (or self-hosted)
├─ Systemd service (python bot)
└─ Nginx (reverse proxy, optional)
```

## Error Handling

### Database Errors
- Connection failures → Retry with exponential backoff
- Constraint violations → Log and notify user
- Transaction failures → Rollback and retry

### LLM Errors
- Rate limit (429) → Retry with backoff
- Invalid token (401) → Log error and stop
- Timeout → Return fallback message
- API error → Log and notify user

### Telegram Errors
- Message too long → Truncate to 4096 chars
- Send failed → Retry up to 3 times
- Chat blocked → Log and continue

## Performance Considerations

### Indexing

Database indexes optimize:
- Conversation history retrieval: `(chat_id, timestamp)`
- User message filtering: `(sender_id)`
- Reply chain following: `(reply_to_message_id)`
- Message lookups: `UNIQUE (message_id, chat_id)`

### Caching (Future)

Potential caching strategies:
- Recent conversation contexts (LRU cache)
- Qdrant search results
- OpenAI embeddings (for repeated phrases)

### Async Processing (Future)

Identify async candidates:
- Document embedding (Phase 2)
- Qdrant indexing (Phase 2)
- Batch embeddings
- PDF processing

## Security Considerations

### Secrets Management
- API keys: Environment variables only, never hardcoded
- Database passwords: Docker secrets or environment
- Telegram token: Rotated regularly

### Database Security
- SQLAlchemy parameterized queries (prevents SQL injection)
- Row-level access control (per-chat isolation)
- Connection pooling with timeout

### API Security
- HTTPS for all external APIs
- Timeout on external calls
- Rate limiting for API calls
- Error messages don't leak sensitive data

## Testing Strategy

### Unit Tests
- Config loading and validation
- Database CRUD operations
- Conversation chain building
- LLM integration (mocked)

### Integration Tests
- End-to-end message flow
- Database persistence
- Multi-user isolation
- Error recovery

### Test Database
- Separate PostgreSQL database (telegram_bot_test)
- Cleaned between test runs
- Uses .env.testing configuration

## Next Steps

For detailed information on specific components:

- **Database Design**: See [DATABASE_DESIGN.md](DATABASE_DESIGN.md)
- **File Organization**: See [FILES_OVERVIEW.md](FILES_OVERVIEW.md)
- **Qdrant Integration**: See [QDRANT_PLANNING.md](../vector-search/QDRANT_PLANNING.md)
- **Configuration**: See [ENVIRONMENTS.md](../setup/ENVIRONMENTS.md)
