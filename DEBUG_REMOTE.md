# Debugging Dev/Prod Embedding Differences (Remote Prod)

## Setup
- **Dev**: Local machine (macOS)
- **Prod**: Ubuntu VPS (remote)
- Both have same config settings but different retrieval results

## Root Cause Hypothesis

Most likely cause: **Prod Qdrant database has different indexed documents than dev.**

Why? The exact same query and settings produce different results:
- Dev: Gets high-score matches (0.81) from "Goalkeeper Q&A" and "Laws of the Game"
- Prod: Gets lower-score matches (0.77) from "IFAB Circular 31"

This suggests the documents in prod's Qdrant are fundamentally different from dev's.

---

## Debugging Steps (Local + Remote)

### Step 1: Run Debug Script Locally

```bash
# On your LOCAL machine
cd /Users/jar/development/telegram-bots/law-of-the-game

# Show what's in dev's vector database
python debug_embeddings.py --show-collection-stats

# Export all docs from dev
python debug_embeddings.py --export-collection /tmp/dev_docs.json --limit 1000

# Test the query on dev
python debug_embeddings.py --query "Если вратарь держит мяч в руках слишком долго, то что за это бывает?"

# Search for goalkeeper documents locally
python debug_embeddings.py --find-document "goalkeeper" --limit 5
```

**Save the output** - you'll need this to compare with prod.

---

### Step 2: Connect to Prod and Run Same Debug Script

```bash
# SSH into prod VPS
ssh your-user@your-prod-ip

# Navigate to project
cd /path/to/law-of-the-game

# Run same commands
python debug_embeddings.py --show-collection-stats

python debug_embeddings.py --export-collection /tmp/prod_docs.json --limit 1000

python debug_embeddings.py --query "Если вратарь держит мяч в руках слишком долго, то что за это бывает?"

python debug_embeddings.py --find-document "goalkeeper" --limit 5
```

---

### Step 3: Compare Results

Key things to check:

1. **Collection Stats:**
   ```
   Dev points_count: ?
   Prod points_count: ?
   ```
   - If different, prod has different data

2. **Exported Documents:**
   - Copy prod's `/tmp/prod_docs.json` to your local machine
   ```bash
   scp your-user@your-prod-ip:/tmp/prod_docs.json /tmp/prod_docs.json
   ```
   - Compare:
   ```bash
   # Count documents
   jq 'length' /tmp/dev_docs.json
   jq 'length' /tmp/prod_docs.json

   # Look for specific documents
   jq '.[] | select(.payload.document_name | contains("Goalkeeper"))' /tmp/dev_docs.json
   jq '.[] | select(.payload.document_name | contains("Goalkeeper"))' /tmp/prod_docs.json

   # Look for IFAB Circular 31
   jq '.[] | select(.payload.document_name | contains("IFAB"))' /tmp/dev_docs.json
   jq '.[] | select(.payload.document_name | contains("IFAB"))' /tmp/prod_docs.json
   ```

3. **Query Embedding:**
   - Compare min/max/mean values from both runs
   - If they match closely, the model is loading correctly
   - If they differ, there's an issue with the model or environment

---

## Most Likely Scenario

Based on your logs:

**Prod has old/wrong data in Qdrant:**
- Prod indexed "IFAB Circular 31" at some point
- Dev was re-indexed with "Goalkeeper Q&A" and newer content
- Prod's Qdrant database wasn't updated

**Solution:** Re-index prod's vector database

```bash
# On prod VPS
ssh your-user@your-prod-ip

cd /path/to/law-of-the-game

# Check what documents are scheduled to index
ls documents/

# Re-index everything
python -m src.cli.document_sync --sync-embeddings

# Or if you have a reset command
make reset-embeddings-prod
```

---

## Alternative: Direct Qdrant Inspection

If you have Qdrant admin access, check directly:

```bash
# On prod VPS
# Connect to Qdrant and list collections
curl http://localhost:6333/collections

# Get collection info
curl http://localhost:6333/collections/documents

# Count points
curl "http://localhost:6333/collections/documents/points?limit=1" | jq '.result.points[0]'
```

---

## Command Reference

### Debug script usage
```bash
# Show collection stats
python debug_embeddings.py --show-collection-stats

# Embed and retrieve for a query
python debug_embeddings.py --query "your question here"

# Export all documents
python debug_embeddings.py --export-collection output.json

# Find documents containing text
python debug_embeddings.py --find-document "goalkeeper"
```

### Comparison commands (Mac/Linux)
```bash
# Count total documents
jq 'length' /tmp/dev_docs.json

# Find unique document names
jq '[.[].payload.document_name] | unique' /tmp/dev_docs.json
jq '[.[].payload.document_name] | unique' /tmp/prod_docs.json

# Compare document names
comm <(jq -r '.[].payload.document_name' /tmp/dev_docs.json | sort | uniq) \
     <(jq -r '.[].payload.document_name' /tmp/prod_docs.json | sort | uniq)
```

---

## Next Action

1. **First:** Run the debug script on both machines
2. **Compare:** Export documents and look for differences in document_name
3. **Identify:** Is "Goalkeeper" missing from prod? Is "IFAB Circular 31" only in prod?
4. **Fix:** Re-index prod with the correct documents

The debug script should give you the answer in 5 minutes!
