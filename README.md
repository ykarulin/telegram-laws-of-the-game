# telegram-laws-of-the-game
Telegram expert in the Laws of the Game with intelligent document selection for enhanced retrieval.

## Features

- 🤖 **AI-Powered Expert**: Uses OpenAI's GPT models to answer football rule questions
- 📚 **RAG (Retrieval-Augmented Generation)**: Searches document database for accurate, cited answers
- 🎯 **Smart Document Selection**: LLM intelligently selects which documents to search (optional)
- 💬 **Telegram Integration**: Simple bot interface for asking questions
- 🔄 **Conversation History**: Maintains context across multiple messages
- 📖 **Proper Citations**: Includes source references for all answers

## Quick Start

### Prerequisites
- Python 3.13+
- PostgreSQL database
- Qdrant vector database
- OpenAI API key
- Telegram Bot Token

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd law-of-the-game

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Run migrations (if applicable)
python -m alembic upgrade head

# Start the bot
python -m src.main
```

## Configuration

### Core Settings

```env
# Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=your_bot_token_here

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4-turbo
OPENAI_MAX_TOKENS=4096

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/db_name

# Qdrant Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=football_documents
```

### RAG Configuration

```env
# Standard RAG Settings
EMBEDDING_MODEL=intfloat/multilingual-e5-large
TOP_K_RETRIEVALS=5
SIMILARITY_THRESHOLD=0.7
```

### Smart Document Selection (Optional)

The bot can intelligently select which documents to search, improving retrieval accuracy:

```env
# Enable/disable smart document selection
ENABLE_DOCUMENT_SELECTION=true

# Maximum tool calls per request (1-20)
MAX_DOCUMENT_LOOKUPS=5

# Maximum chunks per lookup (1-20)
LOOKUP_MAX_CHUNKS=5

# Require tool use or allow fallback
REQUIRE_TOOL_USE=false
```

## Architecture

### Standard RAG Flow
```
User Question → Search All Documents → Mixed Results → LLM Response
```

### With Smart Document Selection (Optional)
```
User Question → LLM Analyzes Question
                  ↓
            LLM Selects Relevant Documents
                  ↓
            Search Selected Documents Only
                  ↓
            Focused, High-Quality Results
                  ↓
            Better LLM Response with Citations
```

### Key Components

- **DocumentLookupTool**: LLM-callable tool for smart document selection
- **RetrievalService**: Handles semantic search and document filtering
- **MessageHandler**: Orchestrates the complete request/response flow
- **EmbeddingService**: Generates vector embeddings for semantic search

## Smart Document Selection

### How It Works

1. **Document List Provided**: LLM is told which documents are available in the knowledge base
2. **Intelligent Selection**: LLM analyzes the user's question and selects relevant documents
3. **Focused Search**: The `lookup_documents` tool searches only selected documents
4. **Better Results**: Returns more relevant chunks with less noise
5. **Graceful Fallback**: If LLM doesn't use the tool, system falls back to standard RAG

### Configuration Options

| Setting | Default | Purpose |
|---------|---------|---------|
| `ENABLE_DOCUMENT_SELECTION` | `true` | Toggle the feature on/off |
| `MAX_DOCUMENT_LOOKUPS` | `5` | Limit how many times LLM can search |
| `LOOKUP_MAX_CHUNKS` | `5` | Limit chunks returned per search |
| `REQUIRE_TOOL_USE` | `false` | Strict mode (requires tool) or flexible (allows fallback) |

### Examples

#### Example 1: Offside Rule Question
```
User: "What is the offside rule?"

LLM Selection: "This is about Laws of the Game, Law 11"
Tool Call: lookup_documents(
    documents=["Laws of Game 2024-25"],
    query="offside rule",
    top_k=3
)
Result: Focused chunks about Law 11 - Offside
Response: Accurate explanation with proper citations
```

#### Example 2: VAR Question
```
User: "How does VAR work in modern football?"

LLM Selection: "This is about VAR procedures"
Tool Call: lookup_documents(
    documents=["VAR Guidelines 2024"],
    query="VAR review procedures",
    top_k=5
)
Result: Specific VAR guidelines
Response: Detailed VAR explanation from authoritative source
```

## Development

### Running Tests

```bash
# Run all tests
make test

# Run specific test file
python -m pytest tests/test_document_lookup_tool.py -v

# Run with coverage
python -m pytest --cov=src
```

### Project Structure

```
src/
├── core/              # Core utilities
│   ├── llm.py         # LLM integration & prompts
│   ├── db.py          # Database connection
│   └── vector_db.py   # Qdrant integration
├── handlers/          # Message processing
│   └── message_handler.py
├── services/          # Business logic
│   ├── retrieval_service.py
│   ├── document_service.py
│   └── embedding_service.py
├── tools/             # LLM-callable tools
│   └── document_lookup_tool.py
└── cli/               # Command-line tools

tests/
├── test_document_lookup_tool.py
└── test_message_handler_document_selection.py
```

### Making Changes

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make changes and add tests
3. Ensure all tests pass: `make test`
4. Commit with clear messages
5. Submit a pull request

## Performance Considerations

### Smart Document Selection Benefits
- **Faster Retrieval**: Searches fewer documents
- **Better Accuracy**: Less noise from irrelevant documents
- **Cost Efficient**: Fewer embeddings to compare

### Disabling Smart Selection
If you prefer the original behavior:
```env
ENABLE_DOCUMENT_SELECTION=false
```

The system will fall back to standard RAG searching all documents.

## Troubleshooting

### No documents available
```
Error: No indexed documents found
```
**Solution**: Ensure documents are uploaded and indexed before running queries.

### Tool not being used
```
LLM not calling lookup_documents tool
```
**Solutions**:
- Verify `ENABLE_DOCUMENT_SELECTION=true`
- Check system prompt in `src/core/llm.py`
- Review LLM logs for tool availability
- Set `REQUIRE_TOOL_USE=true` for strict mode

### Poor retrieval results
- Check similarity threshold: `SIMILARITY_THRESHOLD=0.7`
- Increase `TOP_K_RETRIEVALS` for more candidates
- Verify document embeddings are generated
- Check Qdrant connection and collection status

## Contributing

Contributions are welcome! Please ensure:
- All tests pass
- Code follows existing style
- New features include tests
- Documentation is updated

## License

[Add your license here]

## Support

For issues, questions, or suggestions:
1. Check existing issues and documentation
2. Create a new issue with clear description
3. Include configuration and error messages
4. Provide minimal reproduction steps

---

**Last Updated**: 2025-11-27
**Version**: 1.0.0 with Smart Document Selection
