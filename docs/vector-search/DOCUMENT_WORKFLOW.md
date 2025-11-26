# Document Management Workflow Guide

Complete guide for managing documents in the Football Rules Expert Bot using Qdrant semantic search.

## Overview

The bot uses **Retrieval-Augmented Generation (RAG)** to ground responses in authoritative documents:

1. Documents are parsed and chunked into passages
2. Passages are embedded using OpenAI's embedding model
3. Embeddings are stored in Qdrant vector database
4. When users ask questions, relevant passages are retrieved and injected into the LLM context
5. The LLM generates answers based on retrieved documents

## Quick Start: Auto-Sync Workflow

The fastest way to add documents:

```bash
# 1. Create subfolders for document types (required!)
mkdir -p knowledgebase/upload/laws_of_game
mkdir -p knowledgebase/upload/competition_rules
mkdir -p knowledgebase/upload/referee_manual

# 2. Place documents in appropriate subfolders
#    Subfolder name → becomes document_type
cp laws_of_football_2024.pdf knowledgebase/upload/laws_of_game/
cp referee_signals.txt knowledgebase/upload/referee_manual/
cp competition_rules_2024-25.md knowledgebase/upload/competition_rules/

# 3. Run sync command
make sync-documents

# 4. Verify indexing
make list-documents
```

This automatically:
- ✅ Reads subfolder name → becomes `document_type`
- ✅ Extracts version from filename (e.g., `2024-25`)
- ✅ Detects new/modified documents via SHA256 hashing
- ✅ Uploads to PostgreSQL database
- ✅ Generates OpenAI embeddings
- ✅ Indexes to Qdrant collection
- ✅ Moves files to `documents/indexed/` (preserving folder structure)
- ✅ Tracks state in `.sync_state.json`

## Document Folder Structure

You must organize documents by type in subfolders. The subfolder name becomes the `document_type`.

```
knowledgebase/
├── upload/                              # New documents to process
│   ├── laws_of_game/                   # Subfolder = document_type
│   │   ├── laws_2024-25.pdf            # Version extracted from filename
│   │   └── laws_2023.pdf
│   ├── competition_rules/              # Another document type
│   │   ├── rules_v2.1.md
│   │   └── rules_v2.0.md
│   └── referee_manual/                 # Another document type
│       └── signals_2024.txt
│
├── indexed/                             # Successfully processed (auto-moved)
│   ├── laws_of_game/
│   │   ├── laws_2024-25.pdf            # Files auto-moved here after indexing
│   │   └── laws_2023.pdf
│   ├── competition_rules/
│   │   ├── rules_v2.1.md
│   │   └── rules_v2.0.md
│   └── referee_manual/
│       └── signals_2024.txt
│
├── archive/                             # Deprecated/old documents
│   ├── laws_of_game/
│   │   └── laws_2022.pdf
│   └── competition_rules/
│       └── rules_v1.0.md
│
└── .sync_state.json                    # Auto-generated: tracks processed files
```

### Metadata Extraction Rules

| Location | Field | Source |
|----------|-------|--------|
| Subfolder name | `document_type` | e.g., `laws_of_game`, `competition_rules` |
| Filename | `version` | Extracted patterns: `2024-25`, `v1.2`, `2024`, or empty |
| File content | `name` | Filename (e.g., `laws_2024-25.pdf`) |

**Important:** Files placed directly in `documents/upload/` without a subfolder will get `document_type = "general"`.

### .sync_state.json Format

Tracks processed files to detect changes:

```json
{
  "laws_2024-25.pdf": "a1b2c3d4e5f6...",
  "referee_guide.txt": "f6e5d4c3b2a1...",
  "competition_rules.md": "9z8y7x6w5v4u..."
}
```

Each entry is: `"filename": "SHA256_hash"`

## Supported Document Formats

| Format | Support | Features |
|--------|---------|----------|
| **PDF** (.pdf) | ✅ Full | Text extraction with page numbers |
| **Text** (.txt) | ✅ Full | Plain text, auto-detected encoding |
| **Markdown** (.md) | ✅ Full | Structure-aware parsing |

### Folder Structure Requirements

⚠️ **IMPORTANT:** You MUST create subfolders inside `knowledgebase/upload/` for your document types.

```bash
# CORRECT - Create subfolders by document type
mkdir -p knowledgebase/upload/laws_of_game
mkdir -p knowledgebase/upload/competition_rules
mkdir -p knowledgebase/upload/referee_manual

# Then place files inside these subfolders
cp laws.pdf knowledgebase/upload/laws_of_game/
cp rules.pdf knowledgebase/upload/competition_rules/
```

The subfolder name becomes the `document_type` automatically. Files placed directly in `knowledgebase/upload/` without a subfolder will get `document_type = "general"` (usually not what you want).

### Naming Convention

For automatic version extraction from filenames, use these patterns:
- `document_name_YYYY-MM.pdf` → version: `YYYY-MM`
- `rules_2024-25.pdf` → version: `2024-25`
- `guide_v1.2.pdf` → version: `1.2`
- `laws_2024.pdf` → version: `2024`
- `guide.pdf` → version: empty string (no extraction)

The version pattern is extracted from the filename and stored as document metadata for easy version tracking.

## Auto-Sync Workflow Details

### How `make sync-documents` Works

```
1. Scan knowledgebase/upload/
   ↓
2. Calculate SHA256 hash for each file
   ↓
3. Compare with .sync_state.json
   ↓
4. For each new/modified file:
   a. Create Document record in PostgreSQL
   b. Upload content to database
   c. Generate embeddings via OpenAI API
   d. Index to Qdrant vector database
   e. Move file to knowledgebase/indexed/
   f. Update .sync_state.json
   ↓
5. Report results
```

### Error Handling

If indexing fails for a document:
- PostgreSQL entry status: `failed`
- File remains in `knowledgebase/upload/`
- No file is moved
- Error details logged with timestamp

To retry:
```bash
# Fix the issue (e.g., corrupt file, API error)
# Then run sync again
make sync-documents
```

## Manual CLI Workflow (Advanced)

For fine-grained control, use the CLI directly:

### Upload a Document

```bash
# Basic upload
python -m src.cli upload --file laws_of_game.pdf --type laws_of_game

# With version
python -m src.cli upload \
  --file laws_2024-25.pdf \
  --type laws_of_game \
  --version 2024-25

# With metadata
python -m src.cli upload \
  --file rules.pdf \
  --type competition_rules \
  --version 2024 \
  --description "Complete competition rules"
```

Status after upload: `pending` (not yet indexed to Qdrant)

### List Documents

```bash
# List all documents
python -m src.cli list

# List by type
python -m src.cli list --type laws_of_game

# List by indexing status
python -m src.cli list --status pending    # Not yet indexed
python -m src.cli list --status indexed    # Already indexed
python -m src.cli list --status failed     # Indexing failed
```

Output example:
```
ID  Name                Type             Version  Status    Chunks
1   laws_2024-25.pdf    laws_of_game     2024-25  indexed   156
2   referee_guide.txt   referee_manual   None     pending   42
3   rules_old.pdf       competition      2023     indexed   89
```

### Index Documents

```bash
# Index a specific document by ID
python -m src.cli index --id 2

# Force re-index (re-embed and re-upload to Qdrant)
python -m src.cli index --id 2 --force

# Index all pending documents
python -m src.cli index-pending

# Index with limit (useful for cost control)
python -m src.cli index-pending --limit 3
```

### View Statistics

```bash
# See all pending documents and cost estimate
python -m src.cli stats

# Output shows:
# - Documents by status (pending, indexed, failed)
# - Total pending chunks
# - Estimated OpenAI cost
# - Qdrant collection stats (if available)
```

### Delete Documents

```bash
# Soft delete (marks as deleted, keeps history)
python -m src.cli delete --id 1

# Removes from Qdrant but keeps database record for audit trail
```

## How It Works: End-to-End Flow

### Document Processing Pipeline

```
Input Document (PDF/TXT/MD)
        ↓
PDF Parser / Text Reader
        ↓
Chunk Document (500 chars, 100 char overlap)
        ↓
OpenAI text-embedding-3-small
        ↓
512-dimensional vectors
        ↓
Store in PostgreSQL (embeddings table)
Store in Qdrant (vector collection)
        ↓
Ready for search
```

### Query Retrieval Pipeline

```
User Query: "What is VAR?"
        ↓
OpenAI text-embedding-3-small
        ↓
Query vector: [0.123, -0.456, ...]
        ↓
Qdrant semantic search
        ↓
Top-K similar chunks:
  - "VAR is Video Assistant Referee..."
  - "VAR operator reviews decisions..."
  - "VAR review takes up to 2 minutes..."
        ↓
Format as LLM context:
  === Retrieved Context from Football Documents ===

  [Document 1]
  Source: laws_2024-25.pdf
  Section: Law 5
  Relevance: 92%

  VAR is Video Assistant Referee. A VAR system assists
  the referee in making decisions...

  === End of Retrieved Context ===
        ↓
Inject into LLM prompt (before conversation history)
        ↓
Claude generates answer using documents as primary source
```

## Configuration

### Environment Variables

Set in `.env.development` or `.env.production`:

```bash
# Qdrant settings
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=          # Optional, for cloud Qdrant
QDRANT_COLLECTION_NAME=football_documents

# Search parameters
TOP_K_RETRIEVALS=3           # Number of chunks to retrieve
SIMILARITY_THRESHOLD=0.7     # Min relevance score (0-1)

# OpenAI
OPENAI_API_KEY=your-key-here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

### Chunking Strategy

Documents are split into overlapping chunks:

```
Chunk size:     500 characters
Overlap:        100 characters
Min chunk:      200 characters (discards tiny fragments)

Example:
Law 1: The Field of Play [500 chars]
    ├─ [0:500] "The field shall be..."
    ├─ [400:900] "...rectangular. The field..."
    ├─ [800:1300] "...boundaries. Lines shall..."
    └─ ...

Each chunk gets separate embedding & Qdrant entry
```

## Cost Management

### OpenAI Embedding Costs

Model: `text-embedding-3-small`
- Price: $0.02 per 1M tokens
- Average: ~200 tokens per chunk
- Cost per chunk: ~$0.000004

Example costs:
- 100 documents × 50 chunks = 5,000 chunks = $0.02
- 1,000 documents × 50 chunks = 50,000 chunks = $0.20

### Before Indexing Large Documents

```bash
# Check estimated cost
python -m src.cli stats

# If cost is high, consider:
# 1. Index in batches: python -m src.cli index-pending --limit 10
# 2. Increase chunk size: Edit EmbeddingService.chunk_size
# 3. Remove old documents: python -m src.cli delete --id X
```

## Monitoring & Troubleshooting

### Check Qdrant Health

```bash
# HTTP health check
curl http://localhost:6333/health

# Should return:
# {"status":"ok","version":"0.12.0",...}

# Check collection stats
curl http://localhost:6333/collections/football_documents

# Or use CLI
python -m src.cli stats
```

### View PostgreSQL Data

```bash
# Connect to database
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db

# View documents
SELECT id, name, document_type, qdrant_status, created_at
FROM documents
ORDER BY created_at DESC;

# View embeddings
SELECT id, document_id, chunk_index
FROM embeddings
ORDER BY document_id;

# Exit
\q
```

### Common Issues

**Issue: "Qdrant server not responding"**
```bash
# Check if Qdrant is running
docker-compose ps

# Restart services
make docker-down
make docker-up

# Verify health
curl http://localhost:6333/health
```

**Issue: "Collection not found"**
```bash
# Collection is created on first index
# If missing, ensure:
docker-compose up -d  # Services running
python -m src.cli index-pending  # Triggers collection creation
```

**Issue: "OpenAI API rate limit exceeded"**
```bash
# Wait and retry
# Or index in smaller batches
python -m src.cli index-pending --limit 5
# Wait a minute
python -m src.cli index-pending --limit 5
```

**Issue: "Duplicate document detection warning"**
```bash
# Document with same name exists
# Options:
# 1. Use versioning: laws_2024-25.pdf vs laws_2025-26.pdf
# 2. Use type: laws_of_game vs competition_rules
# 3. Update vs replace existing
```

## Integration Points

### How Documents Are Used During Chat

See [message_handler.py](../../src/handlers/message_handler.py) for integration:

```python
# When user sends message:
1. Retrieve conversation history (if replying)
2. Retrieve relevant documents via RetrievalService
3. Build augmented context: [documents] + [conversation history]
4. Pass to LLM with system prompt
5. LLM uses documents as primary source for accuracy
```

### LLM Context Structure

```
System Prompt: "You are a football rules expert..."

Retrieved Context:
=== Retrieved Context from Football Documents ===
[Document 1] Source: laws_2024-25.pdf, Section: Law 1
...
=== End of Retrieved Context ===

Conversation Context:
[Earlier messages...]

User Query:
What is VAR?
```

## First-Time Setup: Initialize Document Folders

When you first start using the document workflow, set up the folder structure:

```bash
# Create the base knowledgebase folder
mkdir -p knowledgebase/{upload,indexed,archive}

# Create subfolders for your document types
# (Customize these based on your needs)
mkdir -p knowledgebase/upload/laws_of_game
mkdir -p knowledgebase/upload/competition_rules
mkdir -p knowledgebase/upload/referee_manual
mkdir -p knowledgebase/upload/training_materials

# Create corresponding archive folders for old versions
mkdir -p knowledgebase/archive/laws_of_game
mkdir -p knowledgebase/archive/competition_rules
```

Or use this one-liner:

```bash
mkdir -p knowledgebase/{upload,indexed,archive}/{laws_of_game,competition_rules,referee_manual,training_materials}
```

Then you're ready to:
1. Place documents in `knowledgebase/upload/<type>/`
2. Run `make sync-documents`
3. Bot automatically uses indexed documents

## Best Practices

1. **Version Your Documents**
   - Use dates: `laws_2024-25.pdf`
   - Use semantic versions: `rules_v1.0.pdf`
   - Makes it easy to update and archive old versions

2. **Use Appropriate Document Types**
   - `laws_of_game` - Official FIFA Laws of the Game
   - `competition_rules` - League-specific rules
   - `referee_manual` - Referee interpretation guide
   - `training_materials` - Educational documents

3. **Monitor Indexing Costs**
   - Check before indexing large documents: `python -m src.cli stats`
   - Index in batches if cost is high
   - Archive old documents when replacing

4. **Organize Documents**
   - Keep current documents in `documents/indexed/`
   - Move old versions to `documents/archive/`
   - Use meaningful filenames with versions
   - Add descriptions via metadata

5. **Test Retrieval**
   - After indexing, test bot queries in development
   - Verify retrieved passages are relevant
   - Adjust `SIMILARITY_THRESHOLD` if needed
   - Check `TOP_K_RETRIEVALS` setting

## Glossary

- **Embedding**: Vector representation of text (512 dimensions for text-embedding-3-small)
- **Chunk**: Small passage of text (~500 characters)
- **Vector Database (Qdrant)**: Specialized database for semantic similarity search
- **RAG**: Retrieval-Augmented Generation - augmenting LLM with retrieved context
- **Semantic Search**: Finding similar passages by meaning, not just keywords
- **Relevance Score**: Similarity between query and document (0-1, where 1 is identical)

## See Also

- [QDRANT_SETUP.md](./QDRANT_SETUP.md) - Qdrant installation & configuration
- [QDRANT_PLANNING.md](./QDRANT_PLANNING.md) - Implementation roadmap
- [WORKFLOW.md](../getting-started/WORKFLOW.md) - General development workflow
- [DATABASE_DESIGN.md](../development/DATABASE_DESIGN.md) - Database schema details
