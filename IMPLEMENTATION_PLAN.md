# Dynamic Document Selection RAG Implementation Plan

**Status**: Planning Phase
**Created**: 2025-11-27
**Last Updated**: 2025-11-27

---

## Overview

Implement a new RAG approach where the LLM selects which documents to search, instead of searching all documents indiscriminately. This provides:
- **Better retrieval efficiency**: Only search relevant documents
- **Explicit reasoning**: Model reasons about document selection
- **Flexible retrieval**: Model can use lookup tool multiple times
- **Graceful fallback**: Standard RAG if tool is not used

---

## Proposed Architecture

### Current Flow
```
User Query
    ↓
Embed Query
    ↓
Search ALL documents in Qdrant
    ↓
Return top-K chunks (all documents mixed)
    ↓
Format context
    ↓
LLM generates response
```

### New Flow
```
User Query
    ↓
Provide document list to LLM
    ↓
LLM decides which documents are relevant
    ↓
LLM uses lookup_documents tool (multiple times allowed, up to MAX)
    ↓
Tool retrieves chunks from selected documents only
    ↓
Aggregate results from all tool calls
    ↓
Format context
    ↓
LLM generates response with full context
    ↓
[FALLBACK] If tool not used, run standard RAG search
```

---

## Configuration Requirements

New environment variables to add to `.env`:

```
# Maximum number of document lookup tool calls per request
MAX_DOCUMENT_LOOKUPS=5

# Maximum chunks per lookup call
LOOKUP_MAX_CHUNKS=5

# Whether to require tool use (strict mode) or allow fallback
REQUIRE_TOOL_USE=false

# Fallback threshold for automatic RAG if tool not used
FALLBACK_SIMILARITY_THRESHOLD=0.7
```

Updated `Config` class additions:
- `max_document_lookups: int` (default: 5)
- `lookup_max_chunks: int` (default: 5)
- `require_tool_use: bool` (default: False)
- `fallback_similarity_threshold: float` (default: 0.7)

---

## Implementation Components

### 1. Tool Definition Module
**File**: `src/tools/document_lookup_tool.py` (NEW)

Responsibilities:
- Define document lookup tool schema for LLM
- Implement tool execution logic
- Handle document filtering by ID/name
- Apply similarity threshold and top-K filtering
- Return formatted chunks to LLM

Methods:
- `get_tool_schema()` - Returns OpenAI function calling schema
- `execute_lookup(document_names, query, top_k, threshold)` - Core tool logic
- `validate_parameters()` - Validate input parameters

### 2. Document Listing Service
**File**: `src/services/document_service.py` (ENHANCE)

Add new methods:
- `get_indexed_document_names()` - Get list of indexed document names for prompt
- `get_documents_by_names(names: List[str])` - Retrieve document metadata by name list
- `search_in_documents(query, document_ids, top_k, threshold)` - Search in specific documents only

### 3. Retrieval Service Enhancement
**File**: `src/services/retrieval_service.py` (ENHANCE)

Add new methods:
- `retrieve_from_documents(query, document_names, top_k, threshold)` - Search specific documents
- `format_document_list(documents)` - Format document list for LLM prompt
- `should_use_tool_calling()` - Check if tool calling is available

### 4. Message Handler Refactor
**File**: `src/handlers/message_handler.py` (ENHANCE)

Modify flow:
- `_prepare_document_list()` - Get indexed documents for prompt
- `_invoke_document_lookup_tool()` - Execute tool calls from LLM responses
- `_retrieve_documents()` - Refactored to handle both new and fallback approaches
- `_should_use_tool_approach()` - Decide whether to use tool calling

New logic flow in `handle()`:
1. Extract message
2. Load conversation context
3. **[NEW]** Get document list from database
4. **[NEW]** Prepare augmented prompt with document list and tool definition
5. Call LLM with tools enabled
6. **[NEW]** Check if tool was used
7. **[NEW]** If tool used: extract and execute tool calls
8. **[NEW]** Aggregate results from all tool calls
9. **[FALLBACK]** If tool not used: run standard RAG search (maintain compatibility)
10. Format context and generate final response

### 5. Prompt Engineering
**File**: `src/core/llm.py` (ENHANCE)

Create system prompt addendum that:
- Lists available documents to search
- Explains lookup tool purpose and parameters
- Instructs model to search relevant documents first
- Clarifies tool call limits
- Explains fallback behavior

Example system prompt addition:
```
AVAILABLE DOCUMENTS:
{document_list}

DOCUMENT LOOKUP TOOL:
Use the "lookup_documents" tool to search for relevant information in specific documents.
Parameters:
- document_names: List of document names to search (e.g., ["Laws of Game 2024-25"])
- query: Your search query for these documents
- top_k: Number of results to return (1 to {MAX_CHUNKS})
- min_similarity: Minimum similarity threshold (0.0 to 1.0)

You can call this tool up to {MAX_LOOKUPS} times per request.
If you don't use the tool, the system will fall back to searching all documents.
```

---

## Data Flow Diagrams

### Tool Schema (OpenAI Function Calling)

```json
{
  "name": "lookup_documents",
  "description": "Search relevant document sections for information",
  "parameters": {
    "type": "object",
    "properties": {
      "document_names": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Names of documents to search (from available list)",
        "example": ["Laws of Game 2024-25", "VAR Guidelines 2024"]
      },
      "query": {
        "type": "string",
        "description": "Search query for these documents"
      },
      "top_k": {
        "type": "integer",
        "minimum": 1,
        "maximum": "{LOOKUP_MAX_CHUNKS}",
        "default": 3,
        "description": "Number of results to return"
      },
      "min_similarity": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "default": "{SIMILARITY_THRESHOLD}",
        "description": "Minimum similarity threshold"
      }
    },
    "required": ["document_names", "query"]
  }
}
```

### Lookup Response Format

```python
{
  "status": "success",
  "documents_searched": ["Laws of Game 2024-25"],
  "query": "offside rule",
  "results": [
    {
      "document": "Laws of Game 2024-25",
      "section": "Law 11",
      "similarity": 0.94,
      "text": "A player in an offside position..."
    },
    {
      "document": "Laws of Game 2024-25",
      "section": "Law 11 - Offside Position",
      "similarity": 0.89,
      "text": "A player is in an offside position if..."
    }
  ]
}
```

---

## Implementation Phases

### Phase 1: Core Tool Infrastructure
- [x] Explore codebase and understand existing RAG
- [ ] Create `src/tools/document_lookup_tool.py` with schema and execution
- [ ] Add configuration for tool parameters
- [ ] Add test cases for tool validation and execution
- [ ] Document tool interface

### Phase 2: Service Layer Enhancements
- [ ] Enhance `DocumentService` with document listing methods
- [ ] Enhance `RetrievalService` with document-specific search methods
- [ ] Add `format_document_list()` for LLM consumption
- [ ] Add logging for tool calls and results

### Phase 3: Message Handler Integration
- [ ] Refactor `_retrieve_documents()` to support new approach
- [ ] Add document list preparation
- [ ] Add tool invocation logic
- [ ] Add tool result aggregation
- [ ] Maintain fallback to standard RAG
- [ ] Update system prompt with document info and tool definition

### Phase 4: Testing & Validation
- [ ] Unit tests for tool execution
- [ ] Integration tests for message handler flow
- [ ] Test tool calling detection
- [ ] Test fallback behavior
- [ ] Test with various document counts
- [ ] Test error handling

### Phase 5: Documentation & Deployment
- [ ] Update environment example (.env.example)
- [ ] Document configuration options
- [ ] Add usage examples
- [ ] Performance benchmarks (tool vs standard RAG)
- [ ] Monitoring and logging setup

---

## Key Decisions & Rationale

### 1. Tool Calling Implementation
**Decision**: Use OpenAI function calling API (`tools` parameter in API calls)

**Rationale**:
- Native support in Claude/GPT models
- Reliable tool detection and parsing
- Structured parameters with validation
- Easier to track tool usage

**Alternative considered**: Custom prompt-based tool invocation
- Rejected because: Less reliable, harder to parse, model-dependent

### 2. Document Selection Scope
**Decision**: Provide full list of indexed documents to LLM

**Rationale**:
- Enables informed decision-making
- No hidden documents that model can't select
- Clear expectations

**Alternative considered**: Top-N most relevant documents only
- Rejected because: Defeats purpose of model selection

### 3. Fallback Strategy
**Decision**: If LLM doesn't use tool, run standard RAG on ALL documents

**Rationale**:
- Ensures system always works
- No special handling needed
- Graceful degradation
- Maintains backward compatibility

**Alternative considered**: Don't retrieve if tool not used
- Rejected because: Could leave user hanging with generic response

### 4. Configuration Approach
**Decision**: Add new config parameters, keep existing RAG settings

**Rationale**:
- Non-breaking change
- Can control both old and new behavior
- Easier migration path

---

## Error Handling Strategy

### Tool Execution Errors
- Invalid document names: Return informative error, list valid names
- Query embedding failure: Fall back to standard RAG
- Similarity threshold validation: Clamp to valid range
- Top-K validation: Clamp to `[1, LOOKUP_MAX_CHUNKS]`

### Tool Calling Errors
- LLM tool call parse error: Log and fall back to standard RAG
- Missing required parameters: Request retry from LLM
- Tool not available: Fall back to standard RAG

### Aggregation Errors
- Duplicate chunks: Deduplicate by document + section + text
- Empty results from all calls: Gracefully handle, possibly use fallback
- Mixed quality results: Filter by threshold

---

## Testing Strategy

### Unit Tests
- Tool schema validation
- Parameter validation (top_k, threshold, etc.)
- Document list formatting
- Chunk deduplication

### Integration Tests
- Message handler with tool calling
- Tool execution in retrieval flow
- Fallback activation and execution
- Multi-tool-call aggregation

### E2E Tests
- Full message flow with tool calling
- Fallback behavior when tool not used
- Citation generation from tool results
- Various document counts (0, 1, 5, 100 documents)

### Edge Cases
- Empty document list
- All documents with same name
- Very long document names
- Invalid UTF-8 in results
- Rate limiting on embeddings

---

## Monitoring & Metrics

Track in logs:
- Tool use rate (percentage of requests using tool)
- Average tool calls per request
- Tool call success rate
- Fallback activation rate
- Time spent in tool lookup vs standard RAG
- Document selection patterns (which docs are chosen)

---

## Backward Compatibility

**Non-breaking**:
- Can disable tool approach via config (`REQUIRE_TOOL_USE=false`)
- Standard RAG remains functional as fallback
- Existing message handler flow compatible
- No database schema changes

---

## Performance Considerations

### Potential Improvements
- Document list caching (documents don't change often)
- Parallel execution of multiple tool calls
- Caching of document embeddings

### Potential Concerns
- Additional embedding calls for tool parameters
- Larger context window for document list
- More API calls if LLM uses tool multiple times

---

## Next Steps

1. Review this plan and provide feedback
2. Proceed to Phase 1 implementation
3. Begin with tool infrastructure
4. Iteratively test and refine
5. Document learnings and best practices

---

## Appendix: Current System Context

### Key Files
- `src/handlers/message_handler.py` - Current RAG integration
- `src/services/retrieval_service.py` - Retrieval orchestration
- `src/services/document_service.py` - Document management
- `src/core/llm.py` - LLM integration
- `src/config.py` - Configuration management

### Current RAG Settings
- `TOP_K_RETRIEVALS`: 5 (max chunks per search)
- `SIMILARITY_THRESHOLD`: 0.7 (minimum relevance)
- `EMBEDDING_MODEL`: intfloat/multilingual-e5-large
- `EMBEDDING_BATCH_SIZE`: 100

### Database
- PostgreSQL with `documents` table
- Tracks: name, type, version, content, qdrant_status, etc.

### Vector Database
- Qdrant with 1024-dimensional vectors
- Cosine similarity metric
- Collection: `football_documents` (configurable)

---

**Status**: ✅ Planning Complete - Ready for Implementation
**Next**: Await user feedback and approval to proceed with Phase 1
