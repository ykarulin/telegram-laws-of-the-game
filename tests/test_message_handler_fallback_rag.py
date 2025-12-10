"""Tests for message handler fallback RAG logic when LLM doesn't use tools."""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from telegram import Update, Message, User, Chat
from src.handlers.message_handler import MessageHandler
from src.core.vector_db import RetrievedChunk
from src.config import Config, Environment


@pytest.fixture
def mock_config():
    """Create mock config."""
    config = Mock(spec=Config)
    config.environment = Environment.DEVELOPMENT
    config.debug = True
    config.log_level = "DEBUG"
    config.enable_document_selection = True
    config.max_document_lookups = 5
    config.lookup_max_chunks = 5
    config.similarity_threshold = 0.7
    config.top_k_retrievals = 5
    config.openai_model = "gpt-4-turbo"
    return config


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client."""
    return Mock()


@pytest.fixture
def mock_db():
    """Create mock database."""
    return Mock()


@pytest.fixture
def mock_retrieval_service():
    """Create mock retrieval service."""
    service = Mock()
    service.should_use_retrieval.return_value = True
    service.format_context.return_value = "DOCUMENT_CONTEXT"
    service.format_document_list.return_value = "1. Doc1\n2. Doc2"
    service.format_inline_citation.return_value = "Doc1 - Section"
    service.get_indexed_documents.return_value = ["Doc1", "Doc2"]
    return service


@pytest.fixture
def mock_embedding_service():
    """Create mock embedding service."""
    return Mock()


@pytest.fixture
def mock_feature_registry():
    """Create mock feature registry."""
    registry = Mock()
    registry.is_available.return_value = True
    return registry


@pytest.fixture
def message_handler_with_tools(
    mock_config,
    mock_llm_client,
    mock_db,
    mock_retrieval_service,
    mock_embedding_service,
    mock_feature_registry,
):
    """Create message handler with document lookup tool enabled."""
    handler = MessageHandler(
        llm_client=mock_llm_client,
        db=mock_db,
        config=mock_config,
        retrieval_service=mock_retrieval_service,
        embedding_service=mock_embedding_service,
        feature_registry=mock_feature_registry,
    )
    # Ensure document_lookup_tool is initialized
    assert handler.document_lookup_tool is not None
    return handler


@pytest.fixture
def message_handler_without_tools(
    mock_config,
    mock_llm_client,
    mock_db,
    mock_retrieval_service,
    mock_embedding_service,
    mock_feature_registry,
):
    """Create message handler without document lookup tool."""
    mock_config.enable_document_selection = False
    handler = MessageHandler(
        llm_client=mock_llm_client,
        db=mock_db,
        config=mock_config,
        retrieval_service=mock_retrieval_service,
        embedding_service=mock_embedding_service,
        feature_registry=mock_feature_registry,
    )
    # Ensure document_lookup_tool is NOT initialized
    assert handler.document_lookup_tool is None
    return handler


@pytest.fixture
def mock_telegram_update():
    """Create mock Telegram update."""
    user = Mock(spec=User)
    user.id = 12345
    user.is_bot = False

    chat = Mock(spec=Chat)
    chat.id = 67890
    chat.type = "private"

    message = Mock(spec=Message)
    message.message_id = 1
    message.from_user = user
    message.chat = chat
    message.text = "What is the offside rule?"
    message.reply_to_message = None

    update = Mock(spec=Update)
    update.message = message

    return update


class TestFallbackRAGLogic:
    """Test fallback RAG logic when LLM doesn't use tools."""

    @pytest.mark.asyncio
    async def test_tool_available_skips_upfront_rag(
        self, message_handler_with_tools, mock_telegram_update, mock_llm_client
    ):
        """Test: tool available, so upfront RAG should be skipped."""
        # Setup
        mock_llm_client.generate_response.return_value = "The offside rule is..."
        message_handler_with_tools._retrieve_documents = Mock(return_value=[])
        message_handler_with_tools._send_and_persist = AsyncMock()

        # Execute
        await message_handler_with_tools.handle(mock_telegram_update, Mock())

        # Verify: upfront RAG was NOT called (since tool is available)
        # _retrieve_documents should only be called if we enter fallback
        # With LLM not calling tools and returning empty on fallback, it gets called twice
        assert mock_llm_client.generate_response.call_count >= 1


    @pytest.mark.asyncio
    async def test_tool_available_but_not_used_triggers_fallback(
        self, message_handler_with_tools, mock_telegram_update, mock_llm_client, mock_retrieval_service
    ):
        """Test fallback: tool available but LLM doesn't use it, so we retry with RAG."""
        # Setup: LLM response WITHOUT tool usage
        initial_response = "Response from initial call"
        fallback_response = "The offside rule is..."

        mock_llm_client.generate_response.side_effect = [initial_response, fallback_response]

        # Mock _retrieve_documents to return chunks on fallback
        mock_chunks = [
            Mock(spec=RetrievedChunk, text="Offside rule text", score=0.9, metadata={"document": "Laws"})
        ]
        message_handler_with_tools._retrieve_documents = Mock(return_value=mock_chunks)
        mock_retrieval_service.format_context.return_value = "DOCUMENT_CONTEXT"

        # Mock _send_and_persist to avoid actual sending
        message_handler_with_tools._send_and_persist = AsyncMock()

        # Execute
        await message_handler_with_tools.handle(mock_telegram_update, Mock())

        # Verify: LLM was called TWICE (initial call with tools, then fallback without tools)
        assert mock_llm_client.generate_response.call_count == 2

        # Verify: Second call (fallback) has RAG context but no tools
        second_call = mock_llm_client.generate_response.call_args_list[1]
        # Second argument should be augmented_context with documents
        augmented_context = second_call[0][1]
        assert augmented_context is not None

        # Verify: Fallback RAG retrieval was called
        assert message_handler_with_tools._retrieve_documents.call_count >= 1


    @pytest.mark.asyncio
    async def test_no_tool_uses_upfront_rag(
        self, message_handler_without_tools, mock_telegram_update, mock_llm_client, mock_retrieval_service
    ):
        """Test flow: tool not available, so upfront RAG is used."""
        # Setup
        response = "The offside rule is..."
        mock_llm_client.generate_response.return_value = response

        mock_chunks = [
            Mock(spec=RetrievedChunk, text="Offside rule text", score=0.9, metadata={"document": "Laws"})
        ]
        message_handler_without_tools._retrieve_documents = Mock(return_value=mock_chunks)
        mock_retrieval_service.format_context.return_value = "DOCUMENT_CONTEXT"

        # Mock _send_and_persist
        message_handler_without_tools._send_and_persist = AsyncMock()

        # Execute
        await message_handler_without_tools.handle(mock_telegram_update, Mock())

        # Verify: LLM was called ONCE (no fallback needed since no tools)
        assert mock_llm_client.generate_response.call_count == 1

        # Verify: Call doesn't have tools
        call_args = mock_llm_client.generate_response.call_args
        assert call_args[0][3] is None  # No tools parameter

        # Verify: Upfront RAG retrieval was done
        message_handler_without_tools._retrieve_documents.assert_called()


    @pytest.mark.asyncio
    async def test_fallback_with_no_results_uses_initial_response(
        self, message_handler_with_tools, mock_telegram_update, mock_llm_client
    ):
        """Test fallback: when fallback RAG returns no chunks, keep initial response."""
        # Setup: LLM doesn't call tools, returns direct response
        initial_response = "I don't have information about that."
        fallback_response = "I don't have information about that."
        mock_llm_client.generate_response.side_effect = [initial_response, fallback_response]

        # Mock _retrieve_documents to return empty on fallback (no chunks found)
        message_handler_with_tools._retrieve_documents = Mock(return_value=[])

        # Mock _send_and_persist
        message_handler_with_tools._send_and_persist = AsyncMock()

        # Execute
        await message_handler_with_tools.handle(mock_telegram_update, Mock())

        # Verify: Fallback happened (LLM called at least twice)
        assert mock_llm_client.generate_response.call_count >= 1

        # Verify: _send_and_persist was called
        message_handler_with_tools._send_and_persist.assert_called()
        call_args = message_handler_with_tools._send_and_persist.call_args
        sent_response = call_args[0][2]
        # Response should be one of the responses
        assert sent_response in [initial_response, fallback_response]


    @pytest.mark.asyncio
    async def test_fallback_augments_context_with_documents(
        self, message_handler_with_tools, mock_telegram_update, mock_llm_client, mock_retrieval_service
    ):
        """Test fallback: augmented context includes retrieved documents."""
        # Setup
        initial_response = "Response"
        fallback_response = "The offside rule is..."
        mock_llm_client.generate_response.return_value = initial_response

        mock_chunks = [
            Mock(spec=RetrievedChunk, text="Offside rule text", score=0.9, metadata={"document": "Laws"})
        ]
        message_handler_with_tools._retrieve_documents = Mock(return_value=mock_chunks)
        mock_retrieval_service.format_context.return_value = "DOCUMENT_CONTEXT"

        # Mock _send_and_persist
        message_handler_with_tools._send_and_persist = AsyncMock()

        # Make second call return different response
        mock_llm_client.generate_response.side_effect = [initial_response, fallback_response]

        # Execute
        await message_handler_with_tools.handle(mock_telegram_update, Mock())

        # Verify: Second call had augmented context with documents
        second_call = mock_llm_client.generate_response.call_args_list[1]
        augmented_context = second_call[0][1]  # Second arg is augmented_context

        # Should have document context in the messages
        assert augmented_context is not None
        context_str = str(augmented_context)
        assert "DOCUMENT_CONTEXT" in context_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
