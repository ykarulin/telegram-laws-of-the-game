# LLM Response Generation Calling Sequences

This document details the complete calling sequences for the three different flows used to generate LLM responses in the Law of the Game bot.

## Overview

The bot supports three distinct flows depending on whether the document lookup tool is available:

1. **RAG Only Flow**: Tool not available - use upfront retrieval
2. **Tools Flow**: Tool available and LLM uses it
3. **Tools → RAG Fallback Flow**: Tool available but LLM doesn't use it - retry with RAG

---

## Flow 1: RAG Only Flow

**Condition**: Document lookup tool is NOT available (`config.enable_document_selection = false`)

**Use Case**: When document selection is disabled, use traditional RAG with upfront document retrieval.

### Complete Calling Sequence

```
MessageHandler.handle()
├─ MessageData.from_telegram_message()  # Extract message info
│
├─ MessageHandler._load_conversation_context()
│  └─ ConversationDatabase.get_conversation_chain()
│
├─ [RAG RETRIEVAL - UPFRONT]
│  └─ MessageHandler._retrieve_documents()
│     ├─ FeatureRegistry.is_available("rag_retrieval")
│     ├─ RetrievalService.should_use_retrieval()
│     ├─ RetrievalService.retrieve_context()
│     │  ├─ EmbeddingService.encode()  # Generate embeddings
│     │  └─ VectorDB.search()  # Semantic search
│     └─ [Logs retrieval results]
│
├─ [FORMAT CONTEXT]
│  └─ RetrievalService.format_context()  # Format docs for context
│
├─ [GENERATE RESPONSE - NO TOOLS]
│  └─ MessageHandler._generate_response()
│     ├─ [Tools NOT wired - document_lookup_tool is None]
│     ├─ [system_prompt = None → uses default get_system_prompt()]
│     │
│     ├─ [BUILD MESSAGE CONTEXT]
│     ├─ [augmented_context includes RAG documents]
│     │
│     ├─ LLMClient.generate_response()  # FIRST & ONLY LLM CALL
│     │  └─ LLMClient._generate_with_tools()
│     │     └─ OpenAI API call (no tools)
│     │        └─ Returns content directly (no tool_calls)
│     │
│     ├─ [CITATIONS]
│     └─ MessageHandler._append_citations()
│        └─ RetrievalService.format_inline_citation()
│
├─ [SEND & PERSIST]
│  └─ MessageHandler._send_and_persist()
│     ├─ Update.message.reply_text()
│     └─ ConversationDatabase.save_message() [2x: user + bot]
│
└─ [NOTIFICATIONS]
   └─ AdminService.send_info_notification()
```

### Key Characteristics

- **LLM Calls**: 1 (single call with RAG context)
- **Embeddings Generated**: 1 set (upfront)
- **Tool Executor**: Not created
- **System Prompt**: Standard `get_system_prompt()` (no tool instructions)
- **Document Context**: Provided directly in augmented context

---

## Flow 2: Tools Flow

**Condition**: Document lookup tool IS available AND LLM uses the tool

**Use Case**: When document selection is enabled and LLM decides to call the lookup_documents tool.

### Complete Calling Sequence

```
MessageHandler.handle()
├─ MessageData.from_telegram_message()  # Extract message info
│
├─ MessageHandler._load_conversation_context()
│  └─ ConversationDatabase.get_conversation_chain()
│
├─ [NO UPFRONT RAG - tool available, skip upfront retrieval]
│
├─ [GENERATE RESPONSE - WITH TOOLS]
│  └─ MessageHandler._generate_response()
│     ├─ [Tools AVAILABLE - document_lookup_tool exists]
│     │
│     ├─ [GET AVAILABLE DOCUMENTS]
│     │  └─ RetrievalService.get_indexed_documents()
│     │
│     ├─ [CREATE SYSTEM PROMPT WITH TOOLS]
│     │  ├─ RetrievalService.format_document_list()
│     │  └─ LLMClient.get_system_prompt_with_document_selection()
│     │
│     ├─ [CREATE TOOL EXECUTOR WRAPPER]
│     │  └─ tool_executor_wrapper(tool_name, **kwargs)
│     │     └─ [Tracks tool_was_called = True]
│     │
│     ├─ [FIRST LLM CALL - WITH TOOLS]
│     │  └─ LLMClient.generate_response()
│     │     └─ LLMClient._generate_with_tools()  [Iteration 1]
│     │        └─ OpenAI API call (with tools)
│     │           └─ Response: tool_calls=[lookup_documents(...)]
│     │
│     ├─ [TOOL CALL DETECTED]
│     │  └─ response_message.tool_calls != None
│     │
│     ├─ [ADD ASSISTANT MESSAGE WITH TOOL CALL]
│     │  └─ messages.append({
│     │       "role": "assistant",
│     │       "content": None,
│     │       "tool_calls": [...]
│     │     })
│     │
│     ├─ [EXECUTE TOOL CALL]
│     │  └─ LLMClient._execute_tool_call()
│     │     ├─ Parse function arguments (JSON)
│     │     └─ tool_executor("lookup_documents", document_names=[], query="...")
│     │        │
│     │        └─ [TOOL EXECUTOR WRAPPER CALLED]
│     │           ├─ tool_was_called["called"] = True
│     │           ├─ DocumentLookupTool.execute_lookup()
│     │           │  ├─ Validate parameters
│     │           │  ├─ RetrievalService.retrieve_from_documents()
│     │           │  │  ├─ EmbeddingService.encode()  # Generate embedding for query
│     │           │  │  └─ VectorDB.search()  # Search specific documents
│     │           │  └─ [Log tool execution details]
│     │           │
│     │           ├─ DocumentLookupTool.format_result_for_llm()
│     │           └─ Return formatted tool result
│     │
│     ├─ [ADD TOOL RESULT MESSAGE]
│     │  └─ messages.append({
│     │       "role": "tool",
│     │       "tool_call_id": "...",
│     │       "content": "Found X sections...\n..."
│     │     })
│     │
│     ├─ [CONTINUE LOOP FOR SECOND LLM CALL]
│     │  └─ Loop back to iteration 2
│     │
│     ├─ [SECOND LLM CALL - WITH TOOL RESULTS]
│     │  └─ LLMClient._generate_response()  [Iteration 2 in while loop]
│     │     └─ LLMClient._generate_with_tools()
│     │        └─ OpenAI API call (same tools available, but with added context)
│     │           └─ Response: content="Based on the search results..."
│     │
│     ├─ [RETURN RESPONSE]
│     │  └─ return (response, tool_was_called["called"] = True)
│     │
│     └─ [CITATIONS]
│        └─ MessageHandler._append_citations()
│           └─ RetrievalService.format_inline_citation()
│
├─ [SEND & PERSIST]
│  └─ MessageHandler._send_and_persist()
│     ├─ Update.message.reply_text()
│     └─ ConversationDatabase.save_message() [2x: user + bot]
│
└─ [NOTIFICATIONS]
   └─ AdminService.send_info_notification()
```

### Key Characteristics

- **LLM Calls**: 2 (first with tools, second with tool results)
- **Embeddings Generated**: 2 sets (one per search - initial context optional, one for tool query)
- **Tool Executor**: Created and used
- **Tool Calls**: 1 (or more if LLM makes multiple tool calls)
- **System Prompt**: Enhanced with `get_system_prompt_with_document_selection()` (includes tool instructions)
- **Document Context**: Retrieved on-demand via tool, provided to LLM in tool results
- **Tool Usage Tracking**: `tool_was_called["called"] = True`

---

## Flow 3: Tools → RAG Fallback Flow

**Condition**: Document lookup tool IS available BUT LLM doesn't use the tool → fallback to RAG

**Use Case**: When document selection is enabled but LLM decides NOT to call the lookup_documents tool, we retry with augmented RAG context.

### Complete Calling Sequence

```
MessageHandler.handle()
├─ MessageData.from_telegram_message()  # Extract message info
│
├─ MessageHandler._load_conversation_context()
│  └─ ConversationDatabase.get_conversation_chain()
│
├─ [NO UPFRONT RAG - tool available, skip upfront retrieval]
│
├─ [FIRST GENERATION ATTEMPT - WITH TOOLS]
│  └─ MessageHandler._generate_response()
│     ├─ [Tools AVAILABLE - document_lookup_tool exists]
│     │
│     ├─ [GET AVAILABLE DOCUMENTS]
│     │  └─ RetrievalService.get_indexed_documents()
│     │
│     ├─ [CREATE SYSTEM PROMPT WITH TOOLS]
│     │  ├─ RetrievalService.format_document_list()
│     │  └─ LLMClient.get_system_prompt_with_document_selection()
│     │
│     ├─ [CREATE TOOL EXECUTOR WRAPPER]
│     │  └─ tool_executor_wrapper(tool_name, **kwargs)
│     │
│     ├─ [FIRST LLM CALL - WITH TOOLS]
│     │  └─ LLMClient.generate_response()
│     │     └─ LLMClient._generate_with_tools()
│     │        └─ OpenAI API call (with tools)
│     │           └─ Response: content="Response text..." [NO tool_calls]
│     │
│     ├─ [NO TOOL CALL DETECTED]
│     │  └─ response_message.tool_calls == None
│     │
│     └─ return (response, tool_was_called["called"] = False)
│
├─ [CHECK IF FALLBACK NEEDED]
│  └─ if document_lookup_tool and not tool_was_used:
│
├─ [FALLBACK RAG RETRIEVAL]
│  └─ MessageHandler._retrieve_documents()
│     ├─ FeatureRegistry.is_available("rag_retrieval")
│     ├─ RetrievalService.should_use_retrieval()
│     ├─ RetrievalService.retrieve_context()
│     │  ├─ EmbeddingService.encode()  # Generate embeddings
│     │  └─ VectorDB.search()  # Semantic search
│     └─ [Logs retrieval results]
│
├─ [FORMAT FALLBACK CONTEXT]
│  └─ RetrievalService.format_context()
│
├─ [SECOND GENERATION ATTEMPT - WITHOUT TOOLS, WITH RAG]
│  └─ MessageHandler._generate_response_without_tools()
│     ├─ [GET SYSTEM PROMPT - NO TOOLS]
│     │  └─ LLMClient.get_system_prompt()  [Standard prompt]
│     │
│     ├─ [BUILD AUGMENTED CONTEXT WITH RAG]
│     │  └─ [augmented_context includes retrieved documents]
│     │
│     ├─ [SECOND LLM CALL - WITHOUT TOOLS, WITH RAG CONTEXT]
│     │  └─ LLMClient.generate_response()
│     │     └─ LLMClient._generate_with_tools()
│     │        └─ OpenAI API call (no tools, has RAG context)
│     │           └─ Response: content="Response based on documents..."
│     │
│     ├─ [CITATIONS]
│     └─ MessageHandler._append_citations()
│        └─ RetrievalService.format_inline_citation()
│
├─ [SEND & PERSIST]
│  └─ MessageHandler._send_and_persist()
│     ├─ Update.message.reply_text()
│     └─ ConversationDatabase.save_message() [2x: user + bot]
│
└─ [NOTIFICATIONS]
   └─ AdminService.send_info_notification()
```

### Key Characteristics

- **LLM Calls**: 2 (first with tools, second with RAG but no tools)
- **Embeddings Generated**: 2 sets (one optional initial context, one for fallback RAG)
- **Tool Executor**: Created but NOT used
- **Tool Calls**: 0 (LLM never called tools)
- **System Prompt**:
  - First call: Enhanced with tool instructions (`get_system_prompt_with_document_selection()`)
  - Second call: Standard prompt (`get_system_prompt()`)
- **Document Context**:
  - First call: Not provided
  - Second call: Provided directly in augmented context via fallback RAG
- **Tool Usage Tracking**: `tool_was_called["called"] = False` → triggers fallback
- **Retry Logic**: Fallback only happens if `fallback_chunks` is not empty

---

## Flow Comparison Table

| Aspect | RAG Only | Tools | Tools → RAG Fallback |
|--------|----------|-------|----------------------|
| **Tool Available** | ❌ No | ✅ Yes | ✅ Yes |
| **Tool Used** | N/A | ✅ Yes | ❌ No |
| **LLM Calls** | 1 | 2 | 2 |
| **Embedding Calls** | 1 | 1-2* | 2 |
| **Upfront RAG** | ✅ Yes | ❌ No | ❌ No |
| **Fallback RAG** | N/A | N/A | ✅ Yes |
| **System Prompt** | Standard | With Tools | Standard (2nd call) |
| **Total API Calls** | ~1 | ~2 | ~2 |

*In Tools flow, one embedding call is for the tool query if/when LLM calls the tool.

---

## Key Functions and Methods by Flow

### RAG Only Flow Key Methods

```python
MessageHandler.handle()
MessageHandler._retrieve_documents()
MessageHandler._generate_response()  # No tools
RetrievalService.retrieve_context()
RetrievalService.format_context()
LLMClient.generate_response()  # 1 call
LLMClient._generate_with_tools()  # No tools
```

### Tools Flow Key Methods

```python
MessageHandler.handle()
MessageHandler._generate_response()  # With tools
DocumentLookupTool.execute_lookup()
RetrievalService.retrieve_from_documents()
LLMClient.generate_response()  # 2 calls
LLMClient._generate_with_tools()  # Agentic loop
LLMClient._execute_tool_call()
```

### Tools → RAG Fallback Key Methods

```python
MessageHandler.handle()
MessageHandler._generate_response()  # With tools (1st)
MessageHandler._retrieve_documents()  # Fallback RAG
MessageHandler._generate_response_without_tools()  # (2nd)
LLMClient.generate_response()  # 2 calls
RetrievalService.retrieve_context()
RetrievalService.format_context()
```

---

## Decision Logic

### Which Flow Is Used?

```python
# In MessageHandler.handle()

if not self.document_lookup_tool:
    # ← RAG ONLY FLOW
    retrieved_chunks = self._retrieve_documents(message_data.text)
    retrieved_context = self.retrieval_service.format_context(retrieved_chunks)
else:
    # ← TOOLS FLOW (initially)
    retrieved_chunks = []
    retrieved_context = ""

# Generate response
bot_response, tool_was_used = await self._generate_response(...)

# Check if fallback needed
if self.document_lookup_tool and not tool_was_used:
    # ← TOOLS → RAG FALLBACK FLOW
    fallback_chunks = self._retrieve_documents(message_data.text)
    if fallback_chunks:
        bot_response = await self._generate_response_without_tools(...)
```

---

## Message Flow in Tool Calling

When LLM uses tools, the message flow to OpenAI is:

### Iteration 1 (Tool Call)
```
[
  {"role": "system", "content": "...with tool instructions..."},
  {"role": "user", "content": "user query"},
]
↓
OpenAI Response: tool_calls=[...lookup_documents...]
```

### Iteration 2 (Tool Result)
```
[
  {"role": "system", "content": "...with tool instructions..."},
  {"role": "user", "content": "user query"},
  {"role": "assistant", "content": None, "tool_calls": [...]},
  {"role": "tool", "tool_call_id": "...", "content": "Found X sections..."}
]
↓
OpenAI Response: content="Based on the search results..."
```

---

## Performance Implications

| Metric | RAG Only | Tools | Tools → RAG |
|--------|----------|-------|------------|
| **Time** | Fast | Medium-Slow | Slower |
| **Tokens (LLM)** | Medium | Medium | High |
| **Embeddings** | 1 set | 1-2 sets | 2 sets |
| **API Calls** | 1 OpenAI call | 2 OpenAI calls | 2 OpenAI calls |
| **Precision** | Good | Best | Good |

The Tools flow is slower but gives the LLM more control. The fallback ensures document coverage even if the LLM doesn't use tools.

