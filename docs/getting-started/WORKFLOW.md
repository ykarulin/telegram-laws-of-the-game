# Development Workflow

Typical commands and workflows for developing the bot.

## Daily Development Workflow

### Start of Day

```bash
# Open 2 terminals

# Terminal 1: Start services
cd /path/to/law-of-the-game
make docker-up

# Terminal 2: Run bot
cd /path/to/law-of-the-game
make run-dev
```

### Development

Edit code in `src/` as needed. Changes are picked up automatically on next message.

### Testing

```bash
# Terminal 3: Run tests
make test

# Or with coverage
make test-cov

# View HTML report
open htmlcov/index.html
```

### Debugging

Check logs from running services:

```bash
# View all logs
make docker-logs

# Just Qdrant
make docker-logs-qdrant

# Just PostgreSQL
make docker-logs-postgres
```

### End of Day

```bash
# Terminal 2: Stop bot
<Ctrl+C>

# Terminal 1: Stop services
make docker-down
```

## Common Tasks

### Run Tests Before Commit

```bash
make test
make test-cov
```

### Check Code Quality

```bash
# View test coverage
open htmlcov/index.html

# Check test output
make test
```

### Clean Up

```bash
# Remove cache, venv, pytest files
make clean

# Or to reset everything including Docker data:
docker-compose down -v
make clean
```

### Install New Dependencies

```bash
# Add to requirements.txt, then:
source venv/bin/activate
pip install -r requirements.txt

# Or install directly:
pip install package-name
# Then update requirements.txt:
pip freeze > requirements.txt
```

### Switch Environments

```bash
# Development (default)
make run-dev

# Testing
make run-testing

# Production
make run-prod
```

## Debugging Tips

### Bot not responding to messages

1. Check logs:
   ```bash
   make run-dev  # Watch console output
   ```

2. Verify Qdrant is running:
   ```bash
   curl http://localhost:6333/health
   ```

3. Verify PostgreSQL is running:
   ```bash
   docker-compose ps
   ```

### Can't connect to services

```bash
# Check service status
docker-compose ps

# View service logs
make docker-logs

# Restart services
make docker-down
make docker-up
```

### Tests failing

```bash
# Run with verbose output
make test

# See what's failing
make test-cov
open htmlcov/index.html
```

## Git Workflow

Before committing:

```bash
# Run all tests
make test

# Make sure services work
make docker-up
make run-dev   # Test manually
<Ctrl+C>
make docker-down

# Then commit
git add .
git commit -m "Your message"
```

## Multi-Environment Testing

Test bot across environments:

```bash
# Terminal 1: Services
make docker-up

# Terminal 2: Development
make run-dev
# <test>
<Ctrl+C>

# Terminal 2: Testing
make run-testing
# <test>
<Ctrl+C>

# Terminal 1: Stop services
make docker-down
```

## Performance Profiling

Monitor resource usage:

```bash
# Watch Docker container stats
docker stats

# View Qdrant stats
curl http://localhost:6333/telemetry
```

## Database Operations

### Reset Database

```bash
# Reset test database only
docker-compose down -v
make docker-up

# Or run migrations again
source venv/bin/activate
python -m alembic upgrade head
```

### Inspect Database

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db

# Common queries:
SELECT COUNT(*) FROM messages;
SELECT * FROM documents;
```

## Document Management Workflow

The bot uses a document-based RAG (Retrieval-Augmented Generation) system. Documents are indexed in Qdrant for semantic search, and relevant passages are automatically injected into the LLM context when answering questions.

### Quick Start: Auto-Sync Workflow (Recommended)

This is the simplest approach for managing documents:

```bash
# 1. Create subfolders for document types (REQUIRED!)
mkdir -p knowledgebase/upload/laws_of_game
mkdir -p knowledgebase/upload/competition_rules

# 2. Place documents in appropriate subfolders
#    Subfolder name becomes the document_type
cp laws_of_game_2024-25.pdf knowledgebase/upload/laws_of_game/
cp competition_rules.txt knowledgebase/upload/competition_rules/

# 3. Sync documents (auto-upload, index, and organize)
make sync-documents

# 4. Verify documents are indexed
make list-documents
```

The sync command automatically:
- Reads subfolder name → becomes `document_type`
- Extracts version from filename (e.g., `2024-25`, `v1.2`)
- Detects new or modified documents via SHA256 hashing
- Uploads them to PostgreSQL
- Generates OpenAI embeddings
- Indexes to Qdrant vector database
- Moves processed files to `documents/indexed/` (preserving folder structure)
- Tracks processed files in `.sync_state.json`

### Document Folder Structure

You **must** organize documents in subfolders. The subfolder name becomes the `document_type`.

```
knowledgebase/
├── upload/                      # New documents to process
│   ├── laws_of_game/           # Subfolder = document_type
│   │   ├── laws_2024-25.pdf
│   │   └── laws_2023.pdf
│   └── competition_rules/      # Another document type
│       └── rules.txt
├── indexed/                    # Successfully processed (auto-moved)
│   ├── laws_of_game/
│   │   ├── laws_2024-25.pdf
│   │   └── laws_2023.pdf
│   └── competition_rules/
│       └── rules.txt
├── archive/                    # Old/deprecated documents
│   └── laws_of_game/
│       └── laws_2022.pdf
└── .sync_state.json           # Auto-generated: tracks processed files
```

**Metadata Extraction:**
- **Subfolder name** → `document_type` (e.g., `laws_of_game`)
- **Filename** → version extracted (e.g., `2024-25` from `laws_2024-25.pdf`)
- **Files without subfolder** → type defaults to `general`

### Manual CLI Workflow (Advanced)

If you need more control over the indexing process:

```bash
# Upload a document to database
python -m src.cli upload --file laws_of_game.pdf --type laws_of_game --version 2024-25

# List all documents with their indexing status
python -m src.cli list

# List documents by type
python -m src.cli list --type laws_of_game

# List only pending documents (not yet indexed)
python -m src.cli list --status pending

# Index a specific document
python -m src.cli index --id 1

# Index all pending documents at once
python -m src.cli index-pending

# See indexing cost estimate before processing
python -m src.cli stats
```

### Supported Document Formats

- **PDF files** (.pdf) - Text extraction with page numbers
- **Text files** (.txt) - Plain text documents
- **Markdown files** (.md) - Markdown format

### How It Works

When a user sends a question to the bot:

1. **Embedding Generation**: User question is converted to a 512-dimensional embedding using OpenAI's `text-embedding-3-small` model
2. **Semantic Search**: The embedding is sent to Qdrant to find similar document passages
3. **Context Injection**: Top matching passages are formatted and injected into the LLM prompt
4. **Response Generation**: Claude generates an answer grounded in the retrieved documents

Example flow:
```
User: "What is VAR?"
  ↓
Embed query: [0.123, -0.456, ...]  (512 dimensions)
  ↓
Search Qdrant for similar passages
  ↓
Retrieved:
  - "VAR (Video Assistant Referee) is a technology system..."
  - "The VAR operator reviews decisions for..."
  ↓
Inject into LLM context:
  "You are a football rules expert. Use the following context: [passages]"
  ↓
LLM generates answer citing retrieved documents
```

### Monitoring and Troubleshooting

```bash
# Check Qdrant health
curl http://localhost:6333/health

# View PostgreSQL documents table
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db
SELECT id, name, document_type, qdrant_status FROM documents;

# Check Qdrant collection stats
python -m src.cli stats

# View service logs
make docker-logs
```

### Cost Estimation

Document indexing uses OpenAI embeddings API:

- Model: `text-embedding-3-small` ($0.02 per 1M tokens)
- Documents are chunked into 500-character passages with 100-character overlap
- Estimate: ~200 tokens per chunk

Before indexing large documents:
```bash
python -m src.cli stats
# Shows estimated cost for pending documents
```

## Helpful Commands

```bash
# Show all available commands
make help

# View service logs live
make docker-logs

# Clean everything
make clean

# Install dependencies
make install
```
