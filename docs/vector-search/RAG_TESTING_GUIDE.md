# RAG Testing Guide: End-to-End Workflow

Complete guide for testing the Retrieval-Augmented Generation (RAG) system in the Football Rules Expert Bot.

## Overview

This guide covers manual testing of the entire RAG pipeline:
1. Document indexing
2. Query retrieval
3. LLM context augmentation
4. Source citation appending
5. Telegram message delivery

## Prerequisites

- Docker services running (PostgreSQL + Qdrant)
- Bot running in development mode
- Test documents prepared
- Access to Telegram for testing

## Quick Test Setup

### 1. Start Infrastructure

```bash
# Terminal 1: Start Docker services
make docker-up

# Verify services are running
docker-compose ps
curl http://localhost:6333/health  # Qdrant health check
```

### 2. Prepare Test Documents

```bash
# Create document folder structure
mkdir -p knowledgebase/upload/{laws_of_game,competition_rules,referee_manual}

# Add test documents
# Option A: Use real documents
cp ~/Downloads/laws_of_football.pdf knowledgebase/upload/laws_of_game/
cp ~/Downloads/competition_rules.pdf knowledgebase/upload/competition_rules/

# Option B: Create minimal test documents
cat > knowledgebase/upload/laws_of_game/test_laws.txt << 'EOF'
Law 1: The Field of Play

The field of play shall be rectangular. The length of the touchline shall be greater
than the length of the goal line. The field shall be 100-130 yards long and 50-100
yards wide. The field is divided in half by the halfway line.

Law 5: The Referee

The referee enforces the Laws of the Game. The referee has the authority to enforce
the Laws and make decisions on matters not covered by the Laws. The referee is the
sole judge of fact and has the authority to make the final decision.
EOF

cat > knowledgebase/upload/competition_rules/test_rules.txt << 'EOF'
Competition Rules 2024-25

Rule 1: Player Eligibility

Players must be registered with the league. Each team may register up to 25 players
for a season. Substitutes are limited to 12 per match. A player may only play for
one team in the same competition.
EOF
```

### 3. Index Documents

```bash
# Terminal 1: Sync documents (auto-upload and index)
make sync-documents

# Verify indexing completed
make list-documents

# Check document status
python -m src.cli list

# Expected output:
# ID  Name                 Type             Version  Status    Chunks
# 1   test_laws.txt        laws_of_game     None     indexed   5
# 2   test_rules.txt       competition      None     indexed   3
```

### 4. Start Bot

```bash
# Terminal 2: Run bot in development mode
make run-dev

# Watch for logs indicating document loading:
# "Retrieved 3 chunks for document context"
# "Appended citations to response"
```

## Testing Scenarios

### Scenario 1: Basic Query Retrieval

**Test**: Query about Laws of the Game

```
User: What is Law 1 about?
```

**Expected Flow**:
1. Bot receives message
2. Query embedded using OpenAI API
3. Qdrant searches for similar chunks
4. Retrieved context injected into LLM prompt
5. LLM generates response citing documents
6. Citations appended to response

**Expected Output**:
```
The Field of Play is the subject of Law 1. It describes that the field
shall be rectangular with specific dimensions (100-130 yards long,
50-100 yards wide) and divided in half by the halfway line.

[Source: test_laws.txt, Law 1]
```

### Scenario 2: Multiple Document References

**Test**: Query requiring multiple document sources

```
User: What are the key rules about players?
```

**Expected Flow**:
1. Query embedded
2. Qdrant finds relevant chunks from multiple documents
3. Both laws_of_game and competition_rules chunks retrieved
4. Context formatted with both documents
5. LLM generates comprehensive answer
6. Unique citations from each document appended

**Expected Output**:
```
Players have specific requirements... [Law content]
Additionally, competition rules specify... [Rules content]

[Source: test_laws.txt, Law 5]
[Source: test_rules.txt, Rule 1]
```

### Scenario 3: No Relevant Documents

**Test**: Query with no matching documents

```
User: How many points is a goal worth in tennis?
```

**Expected Flow**:
1. Query embedded
2. Qdrant searches but finds no matches above similarity threshold
3. Retrieved context is empty
4. LLM responds with general knowledge only
5. No citations appended

**Expected Output**:
```
I don't have information about tennis in the knowledge base.
However, in football, a goal is worth 3 points if you win,
1 point if you draw...
```

### Scenario 4: Telegram Message Length Limits

**Test**: Very detailed query resulting in long response

```
User: Provide a comprehensive summary of all rules and laws
```

**Expected Flow**:
1. Query retrieves many chunks
2. LLM generates long comprehensive response
3. Total length (response + citations) exceeds 4096 chars
4. Response is truncated at sentence boundary
5. Citations still appended
6. Message sent successfully

**Check Logs**:
```
"Response truncated from 4500 to 3900 chars to fit citations"
```

### Scenario 5: Conversation Context

**Test**: Follow-up questions in conversation

```
User: What is a referee?
Bot: [Response about Law 5: The Referee]

User: What are their powers? (reply to bot's message)
```

**Expected Flow**:
1. Detects reply to previous message
2. Retrieves previous conversation
3. Retrieves new documents for current query
4. Augments context with both conversation + documents
5. LLM generates answer considering conversation history
6. Citations for new retrieval only

**Check Logs**:
```
"Built conversation context with 2 context items from 2 messages"
"Retrieved 2 chunks for document context"
"Appended citations to response"
```

## Testing Checklist

### Document Indexing
- [ ] Documents placed in correct subfolders
- [ ] `make sync-documents` completes without errors
- [ ] `make list-documents` shows all documents as "indexed"
- [ ] Database has correct document metadata (type, version)
- [ ] Qdrant collection has expected number of chunks

### Query Retrieval
- [ ] Query returns relevant chunks (not empty results)
- [ ] Top chunk has highest similarity score (0.8+)
- [ ] Retrieved text matches document content
- [ ] Metadata (document_name, section) is populated

### Citation Formatting
- [ ] Citations appear after response (not mixed in)
- [ ] Citations include document name and section
- [ ] No duplicate citations from same document
- [ ] Citations format: `[Source: Document, Section]`

### Message Delivery
- [ ] Response received in Telegram chat
- [ ] Response text is readable and complete
- [ ] Citations are visible in message
- [ ] Message sent successfully (no timeout)
- [ ] No truncation visible (unless very long)

### Edge Cases
- [ ] Empty query handled gracefully
- [ ] Very long document processed correctly
- [ ] Multiple documents with same name behave correctly
- [ ] Emoji and special characters in documents work
- [ ] Non-ASCII characters (accents, etc.) work

## Debugging Commands

### Check Qdrant Collection

```bash
# View collection health
curl http://localhost:6333/health

# Get collection stats
curl http://localhost:6333/collections/football_documents

# View recent operations
docker-compose logs -f qdrant
```

### Check PostgreSQL Documents

```bash
# Connect to database
docker-compose exec postgres psql -U telegram_bot -d telegram_bot_db

# View documents table
SELECT id, name, document_type, qdrant_status, created_at
FROM documents
ORDER BY created_at DESC
LIMIT 5;

# View embeddings
SELECT COUNT(*) as total_embeddings FROM embeddings;
SELECT document_id, COUNT(*) as chunks
FROM embeddings
GROUP BY document_id;

# View messages with citations
SELECT id, text, created_at FROM messages
WHERE sender_type = 'bot'
ORDER BY created_at DESC
LIMIT 3;
```

### Check Bot Logs

```bash
# View real-time logs
make run-dev  # Shows in current terminal

# View retrieval debug info
grep "Retrieved" debug.log
grep "citation" debug.log
grep "truncated" debug.log

# View errors
grep "Error" debug.log
grep "WARNING" debug.log
```

### Test Specific Component

```bash
# Test retrieval service directly
python3 << 'EOF'
from src.config import Config
from src.services.retrieval_service import RetrievalService
from src.services.embedding_service import EmbeddingService

config = Config.from_env()
embedding_svc = EmbeddingService(config)
retrieval_svc = RetrievalService(config, embedding_svc)

# Test retrieval
query = "What is the field of play?"
chunks = retrieval_svc.retrieve_context(query)

print(f"Retrieved {len(chunks)} chunks")
for chunk in chunks:
    print(f"  - Score: {chunk.score:.2f}")
    print(f"  - Text: {chunk.text[:100]}...")
    if chunk.metadata:
        print(f"  - Source: {chunk.metadata.get('document_name')}")
EOF
```

## Performance Monitoring

### Measure Retrieval Speed

```bash
# Add timing to message handler logs
# Check how long retrieval takes

import time
start = time.time()
chunks = service.retrieve_context(query)
elapsed = time.time() - start
print(f"Retrieval took {elapsed:.2f}s")
```

### Monitor OpenAI Costs

```bash
# Check embedding cost before indexing
python -m src.cli stats

# Output shows:
# - Pending documents: 5
# - Total chunks: 250
# - Estimated cost: $0.001 (250 chunks × 4 tokens × $0.02/1M)
```

### Check Message Size

```bash
# Before sending to Telegram, measure response
response = "..."
citations = "..."
total = len(response) + len(citations)

print(f"Response: {len(response)} chars")
print(f"Citations: {len(citations)} chars")
print(f"Total: {total} chars")
print(f"Telegram limit: 4096 chars")
print(f"Room for more: {4096 - total} chars")
```

## Common Issues & Solutions

### Issue: "No relevant documents found"

**Symptoms**: All queries return empty retrieval

**Causes**:
- Documents not indexed yet
- Similarity threshold too high
- Wrong query phrasing

**Solutions**:
```bash
# Verify documents are indexed
make list-documents
python -m src.cli stats

# Lower similarity threshold temporarily
SIMILARITY_THRESHOLD=0.5 make run-dev

# Test with exact document text
User: "Law 1: The Field of Play"  # Should match perfectly
```

### Issue: "Qdrant server not responding"

**Symptoms**: Retrieval completely fails

**Solutions**:
```bash
# Check if service is running
docker-compose ps

# Restart if needed
make docker-down
make docker-up

# Verify health
curl http://localhost:6333/health
```

### Issue: "Citations duplicated or malformed"

**Symptoms**: Multiple copies of same citation, missing sections

**Solutions**:
- Verify chunk metadata has document_name set
- Check that sections are not empty
- Ensure format_inline_citation is using correct fields

```bash
# Debug citation generation
chunk = chunks[0]
citation = service.format_inline_citation(chunk)
print(f"Citation: {citation}")
print(f"Metadata: {chunk.metadata}")
```

### Issue: "Response truncated too much"

**Symptoms**: Important information cut off to fit citations

**Solutions**:
- Reduce number of retrieved chunks (TOP_K_RETRIEVALS)
- Shorten citation format
- Remove similarity scores from context

```bash
# Config
TOP_K_RETRIEVALS=2  # Instead of 3
SIMILARITY_THRESHOLD=0.75  # Only best matches
```

## Testing with Real Documents

### Using Official Laws of the Game

1. Download from FIFA website (PDF)
2. Place in `knowledgebase/upload/laws_of_game/`
3. Run `make sync-documents`
4. Test queries like:
   - "What is offside?"
   - "How long is a match?"
   - "What is a penalty?"

### Using Competition Rules

1. Add your league/tournament rules
2. Place in `knowledgebase/upload/competition_rules/`
3. Test cross-document queries

### Versioning for A/B Testing

```bash
# Store multiple versions
knowledgebase/upload/laws_of_game/
  ├── laws_2024-25.pdf  (new)
  ├── laws_2023-24.pdf  (old)
  └── laws_2022-23.pdf  (archive)

# Archive old ones after testing
mv knowledgebase/indexed/laws_of_game/laws_2022-23.pdf \
   knowledgebase/archive/laws_of_game/
```

## Automated Testing

### Unit Tests

```bash
# Run tests
make test

# With coverage
make test-cov
open htmlcov/index.html
```

### Integration Tests

Create `tests/test_rag_integration.py`:

```python
@pytest.mark.asyncio
async def test_rag_pipeline_end_to_end():
    """Test complete RAG flow: index -> retrieve -> cite."""
    # 1. Index document
    # 2. Query with retrieval
    # 3. Verify chunks retrieved
    # 4. Verify citations appended
    # 5. Verify response valid
```

## Success Criteria

The RAG system is working correctly when:

1. ✅ Documents are indexed and searchable
2. ✅ Queries return relevant chunks (0.7+ similarity)
3. ✅ LLM responses include source citations
4. ✅ Citations format correctly (no duplicates)
5. ✅ Telegram messages deliver successfully (< 4096 chars)
6. ✅ Conversation context preserved in follow-ups
7. ✅ Edge cases handled (no results, very long responses)
8. ✅ Performance acceptable (< 2s per query)
9. ✅ Costs tracked (< $1 per 1000 queries)

## Next Steps

After successful testing:

1. **Deploy to Production**
   - Review deployment guide
   - Set up monitoring
   - Plan document update schedule

2. **Monitor Quality**
   - Track user satisfaction
   - Monitor citation accuracy
   - Track cost per query
   - Monitor retrieval performance

3. **Iterate**
   - Adjust TOP_K_RETRIEVALS based on feedback
   - Update documents regularly
   - Refine similarity threshold
   - Add new document types

## See Also

- [DOCUMENT_WORKFLOW.md](./DOCUMENT_WORKFLOW.md) - Document management
- [QDRANT_SETUP.md](./QDRANT_SETUP.md) - Qdrant configuration
- [WORKFLOW.md](../getting-started/WORKFLOW.md) - General development
- [ARCHITECTURE.md](../development/ARCHITECTURE.md) - System design
