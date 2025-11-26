# Qdrant Vector Database Setup Guide

## Overview

Qdrant is a vector database used to store document embeddings for semantic search. The bot retrieves relevant document sections from Qdrant to ground LLM responses in authoritative documents.

## Architecture

```
┌─────────────────────────────────────────────┐
│    Football Rules Bot (Python)              │
│  • src/core/vector_db.py (client)           │
│  • qdrant-client library                    │
└────────────┬────────────────────────────────┘
             │ gRPC/HTTP API
             ↓ localhost:6333
┌─────────────────────────────────────────────┐
│    Qdrant Server                            │
│  • Vector storage & indexing                │
│  • Semantic search engine                   │
│  • Collections: football_documents          │
└─────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────┐
│    Persistent Storage                       │
│  • Docker volume: qdrant_data               │
│  • Or: PostgreSQL JSONB (document metadata) │
└─────────────────────────────────────────────┘
```

## Quick Start (Docker - Recommended)

### Prerequisites
- Docker and Docker Compose installed
- `.env.development` configured with Qdrant settings

### Start All Services

```bash
# Navigate to project root
cd /path/to/law-of-the-game

# Start PostgreSQL and Qdrant
docker-compose up -d

# Verify services are running
docker-compose ps

# Check logs
docker-compose logs -f qdrant
docker-compose logs -f postgres
```

### Verify Qdrant is Running

```bash
# Check health
curl http://localhost:6333/health

# Should return: {"status":"ok"}

# View collections
curl http://localhost:6333/collections
```

### Stop Services

```bash
docker-compose down

# To also remove volumes (clears all data):
docker-compose down -v
```

## Setup Options

### Option 1: Docker Compose (Development - Easiest)

**Pros:**
- One command to start everything
- Isolated environment
- Persistent storage via volumes
- Easy to reset/clean

**Cons:**
- Requires Docker installation

**Steps:**
```bash
docker-compose up -d qdrant
```

Service will be available at `localhost:6333`

---

### Option 2: Docker Direct

**Start Qdrant only:**
```bash
docker run -d \
  --name law-of-the-game-qdrant \
  -p 6333:6333 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant:latest
```

**Stop:**
```bash
docker stop law-of-the-game-qdrant
docker rm law-of-the-game-qdrant
```

---

### Option 3: Binary Installation (macOS)

**Install:**
```bash
brew install qdrant
```

**Start:**
```bash
qdrant
```

**Stop:** Press Ctrl+C

Service will be available at `localhost:6333`

---

### Option 4: Qdrant Cloud (Production)

For production deployments, use Qdrant Cloud:

1. Sign up at https://cloud.qdrant.io
2. Create a cluster and get credentials
3. Update `.env.production`:
   ```
   QDRANT_HOST=your-cluster-url.qdrant.io
   QDRANT_PORT=6333
   QDRANT_API_KEY=your_api_key_here
   ```
4. No local setup needed

---

### Option 5: Kubernetes (Advanced)

For large deployments, Qdrant can be deployed to Kubernetes. See [Qdrant Helm Charts](https://github.com/qdrant/qdrant-helm).

---

## Configuration

### Environment Variables

All Qdrant settings are configured via `.env.*` files:

```bash
# .env.development (local development)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=                    # Empty for local
QDRANT_COLLECTION_NAME=football_documents

# .env.testing (unit tests)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=football_documents_test

# .env.production (cloud)
QDRANT_HOST=your-cluster.qdrant.io
QDRANT_PORT=6333
QDRANT_API_KEY=your_secure_key
QDRANT_COLLECTION_NAME=football_documents
```

### Embedding Configuration

```bash
# Text chunking settings
EMBEDDING_BATCH_SIZE=100           # Chunks per embedding request
TOP_K_RETRIEVALS=5                 # Results returned per query
SIMILARITY_THRESHOLD=0.7            # Minimum relevance score

# Embedding model
EMBEDDING_MODEL=text-embedding-3-small
```

---

## Database Collections

### football_documents (Development/Production)

Stores document chunks with metadata:

**Vector Size:** 512 dimensions (text-embedding-3-small)

**Distance Metric:** COSINE (similarity 0.0-1.0, where 1.0 = exact match)

**Metadata per chunk:**
```json
{
  "document_id": 123,
  "document_name": "Laws of the Game 2024-25",
  "document_type": "laws_of_game",
  "section": "Law 1: The Field of Play",
  "subsection": "Dimensions",
  "page_number": 5,
  "version": "2024-25",
  "text": "The field of play shall be rectangular..."
}
```

### football_documents_test (Testing)

Separate collection for unit tests, cleared between test runs.

---

## Troubleshooting

### Qdrant Won't Start

**Docker error: Port 6333 already in use**
```bash
# Find what's using the port
lsof -i :6333

# Kill the process or use a different port
docker run -p 6334:6333 qdrant/qdrant:latest
# Then update QDRANT_PORT in .env
```

**Connection refused**
```bash
# Check if service is running
docker-compose ps
curl http://localhost:6333/health

# If not running:
docker-compose up -d qdrant
```

### Collection Already Exists

When uploading documents, if a collection already exists with the same name, it won't be recreated. This is correct behavior—existing data is preserved.

To reset (testing only):
```python
from src.core.vector_db import VectorDatabase
from src.config import load_config

config = load_config()
db = VectorDatabase(
    host=config.qdrant_host,
    port=config.qdrant_port,
    api_key=config.qdrant_api_key
)

# Delete collection and all data
db.delete_collection(config.qdrant_collection_name)

# Recreate empty
db.create_collection(config.qdrant_collection_name)
```

### High Memory Usage

Qdrant loads indexes into memory. Adjust Docker limits:

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    mem_limit: 2g          # Limit to 2GB
    memswap_limit: 2g
```

---

## Monitoring

### Health Check

```bash
curl http://localhost:6333/health
# Response: {"status":"ok"}
```

### View Statistics

```bash
curl http://localhost:6333/telemetry
```

### Check Collection Info

```bash
curl http://localhost:6333/collections/football_documents
```

### Web UI (Optional)

Qdrant provides a web UI for visualization. Access via:
- Browser: http://localhost:6333/dashboard (if enabled in Qdrant config)

---

## Performance Tuning

### Embedding Batch Size

Larger batches = faster but more memory:
```
EMBEDDING_BATCH_SIZE=50   # Conservative (low memory)
EMBEDDING_BATCH_SIZE=100  # Balanced (recommended)
EMBEDDING_BATCH_SIZE=200  # Aggressive (more memory)
```

### Similarity Threshold

Higher threshold = fewer but more relevant results:
```
SIMILARITY_THRESHOLD=0.5   # Liberal (may return noise)
SIMILARITY_THRESHOLD=0.7   # Balanced (recommended)
SIMILARITY_THRESHOLD=0.9   # Strict (may miss relevant docs)
```

### Top-K Retrievals

More results = slower but more context for LLM:
```
TOP_K_RETRIEVALS=3    # Fast, minimal context
TOP_K_RETRIEVALS=5    # Balanced (recommended)
TOP_K_RETRIEVALS=10   # Slow, rich context
```

---

## Persistence & Backups

### Docker Volumes

Data is stored in Docker volume `qdrant_data`:

```bash
# Inspect volume
docker volume inspect qdrant_data

# Backup volume
docker run --rm -v qdrant_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/qdrant_backup.tar.gz /data

# Restore volume
docker run --rm -v qdrant_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/qdrant_backup.tar.gz -C /
```

### Qdrant Cloud

Backups are handled by Qdrant Cloud automatically.

---

## API Reference

### Python Client Usage

```python
from src.config import load_config
from src.core.vector_db import VectorDatabase
from qdrant_client.models import PointStruct

# Initialize
config = load_config()
db = VectorDatabase(
    host=config.qdrant_host,
    port=config.qdrant_port,
    api_key=config.qdrant_api_key
)

# Create collection
db.create_collection("my_collection", vector_size=512)

# Add vectors
points = [
    PointStruct(
        id=1,
        vector=[0.1, 0.2, ...],  # 512-dim vector
        payload={
            "text": "Document content",
            "source": "laws_of_game"
        }
    )
]
db.upsert_points("my_collection", points)

# Search
results = db.search(
    collection_name="my_collection",
    query_vector=[0.15, 0.25, ...],
    limit=5,
    min_score=0.7
)

for chunk in results:
    print(f"Score: {chunk.score}")
    print(f"Text: {chunk.text}")
    print(f"Metadata: {chunk.metadata}")
```

---

## Next Steps

1. **Start Qdrant:** `docker-compose up -d`
2. **Verify connection:** Test in Python
3. **Upload documents:** See [DOCUMENT_MANAGEMENT.md](DOCUMENT_MANAGEMENT.md)
4. **Monitor:** Check logs and health endpoint

---

## References

- [Qdrant Official Docs](https://qdrant.tech/documentation/)
- [Qdrant Python Client](https://github.com/qdrant/qdrant-client)
- [Docker Hub: qdrant/qdrant](https://hub.docker.com/r/qdrant/qdrant)
- [Qdrant Cloud](https://cloud.qdrant.io/)
