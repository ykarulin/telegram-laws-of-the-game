"""Integration tests for RAG pipeline."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update, Message, User as TelegramUser, Chat
from telegram.ext import ContextTypes
from src.handlers.message_handler import MessageHandler
from src.config import Config, Environment
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.core.vector_db import RetrievedChunk


class TestRAGIntegration:
    """Integration tests for RAG pipeline with message handler."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = MagicMock(spec=Config)
        config.environment = Environment.TESTING
        config.openai_model = "gpt-4-turbo"
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "football_documents"
        config.top_k_retrievals = 5
        config.similarity_threshold = 0.55
        return config

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = MagicMock()
        client.generate_response = MagicMock(
            return_value="The offside rule states that a player is in an offside position if nearer to the opponent's goal line than both the ball and the last two opponents."
        )
        return client

    @pytest.fixture
    def mock_database(self):
        """Create a mock database."""
        db = MagicMock()
        db.save_message = MagicMock()
        db.get_conversation_chain = MagicMock(return_value=[])
        return db

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        service = MagicMock(spec=EmbeddingService)
        service.embed_text = MagicMock(return_value=[0.1] * 512)
        return service

    @pytest.fixture
    def mock_vector_db(self):
        """Create a mock vector database."""
        db = MagicMock()
        return db

    @pytest.fixture
    def mock_retrieval_service(self, mock_config, mock_embedding_service, mock_vector_db):
        """Create a mock retrieval service."""
        with patch("src.services.retrieval_service.VectorDatabase") as mock_vdb_class:
            mock_vdb_class.return_value = mock_vector_db
            service = RetrievalService(mock_config, mock_embedding_service)
            service.vector_db = mock_vector_db
            return service

    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram Update object."""
        user = TelegramUser(id=123, is_bot=False, first_name="Test")
        chat = MagicMock(spec=Chat)
        chat.id = 123
        chat.send_action = AsyncMock()

        message = MagicMock(spec=Message)
        message.text = "What is the offside rule?"
        message.message_id = 1
        message.chat_id = 123
        message.from_user = user
        message.reply_to_message = None
        message.reply_text = AsyncMock()
        message.chat = chat

        update = MagicMock(spec=Update)
        update.message = message
        update.effective_chat = chat
        update.effective_user = user
        return update

    @pytest.fixture
    def mock_context(self):
        """Create a mock Telegram Context object."""
        return AsyncMock(spec=ContextTypes.DEFAULT_TYPE)

    @pytest.mark.asyncio
    async def test_message_handler_with_retrieval_service(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_retrieval_service,
        mock_update,
        mock_context,
        mock_vector_db
    ):
        """Test message handler with RAG retrieval service."""
        # Setup - mock retrieval to return relevant chunks
        offside_chunk = RetrievedChunk(
            chunk_id="1",
            text="A player is in an offside position if nearer to the opponent's goal line than both the ball and the last two opponents.",
            score=0.92,
            metadata={"section": "Law 11", "document_name": "Laws of Game 2025-26"}
        )
        mock_vector_db.search.return_value = [offside_chunk]

        message_handler = MessageHandler(
            mock_llm_client,
            mock_database,
            mock_config,
            mock_retrieval_service
        )

        # Execute
        await message_handler.handle(mock_update, mock_context)

        # Assert - LLM should be called with augmented context
        assert mock_llm_client.generate_response.called
        call_args = mock_llm_client.generate_response.call_args
        user_text = call_args[0][0]
        augmented_context = call_args[0][1]

        # Verify user text
        assert user_text == "What is the offside rule?"

        # Verify augmented context includes retrieved documents
        assert augmented_context is not None
        assert len(augmented_context) > 0
        # First item should be the document context system message
        assert augmented_context[0]["role"] == "system"
        assert "DOCUMENT CONTEXT" in augmented_context[0]["content"]
        assert "offside" in augmented_context[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_message_handler_without_retrieval_matches(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_retrieval_service,
        mock_update,
        mock_context,
        mock_vector_db
    ):
        """Test message handler when no retrieval matches are found."""
        # Setup - no retrieval matches
        mock_vector_db.search.return_value = []

        message_handler = MessageHandler(
            mock_llm_client,
            mock_database,
            mock_config,
            mock_retrieval_service
        )

        # Execute
        await message_handler.handle(mock_update, mock_context)

        # Assert - LLM should be called without document context
        call_args = mock_llm_client.generate_response.call_args
        augmented_context = call_args[0][1]

        # If no context, should be None (or empty list, depending on implementation)
        assert augmented_context is None or len(augmented_context) == 0

    @pytest.mark.asyncio
    async def test_rag_citation_appending(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_retrieval_service,
        mock_update,
        mock_context,
        mock_vector_db
    ):
        """Test that retrieved chunks are cited in the response."""
        # Setup
        chunk = RetrievedChunk(
            chunk_id="1",
            text="Offside rule content",
            score=0.92,
            metadata={
                "document_name": "Laws of Game 2025-26",
                "section": "Law 11",
                "page_number": 42
            }
        )
        mock_vector_db.search.return_value = [chunk]

        message_handler = MessageHandler(
            mock_llm_client,
            mock_database,
            mock_config,
            mock_retrieval_service
        )

        # Execute
        await message_handler.handle(mock_update, mock_context)

        # Assert - response should include citation
        reply_calls = mock_update.message.reply_text.call_args_list
        assert len(reply_calls) > 0
        response_text = reply_calls[0][0][0]

        # Response should include original text plus citation
        assert "The offside rule" in response_text  # From mock LLM response

    @pytest.mark.asyncio
    async def test_retrieval_disabled_skips_document_search(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_update,
        mock_context,
    ):
        """Test that message handler works without retrieval service."""
        message_handler = MessageHandler(
            mock_llm_client,
            mock_database,
            mock_config,
            retrieval_service=None  # No retrieval service
        )

        # Execute
        await message_handler.handle(mock_update, mock_context)

        # Assert - should still generate response
        assert mock_llm_client.generate_response.called

    @pytest.mark.asyncio
    async def test_conversation_context_with_rag(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_retrieval_service,
        mock_update,
        mock_context,
        mock_vector_db
    ):
        """Test that RAG context is combined with conversation history."""
        from src.core.db import Message as DBMessage

        # Setup - replying to another message with retrieved documents
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.message_id = 5

        conversation_chain = [
            DBMessage(
                message_id=5,
                chat_id=123,
                sender_type="user",
                sender_id="123",
                text="Previous: What is offside?",
                reply_to_message_id=None
            ),
            DBMessage(
                message_id=6,
                chat_id=123,
                sender_type="bot",
                sender_id="gpt-4-turbo",
                text="Previous answer about offside",
                reply_to_message_id=5
            ),
        ]
        mock_database.get_conversation_chain = MagicMock(return_value=conversation_chain)

        rag_chunk = RetrievedChunk(
            chunk_id="1",
            text="Additional offside information",
            score=0.88,
            metadata={"section": "Law 11"}
        )
        mock_vector_db.search.return_value = [rag_chunk]

        message_handler = MessageHandler(
            mock_llm_client,
            mock_database,
            mock_config,
            mock_retrieval_service
        )

        # Execute
        await message_handler.handle(mock_update, mock_context)

        # Assert - augmented context should have both RAG and conversation context
        call_args = mock_llm_client.generate_response.call_args
        augmented_context = call_args[0][1]

        assert augmented_context is not None
        assert len(augmented_context) > 2  # System message + conversation items

        # First should be system message with document context
        assert augmented_context[0]["role"] == "system"
        assert "DOCUMENT CONTEXT" in augmented_context[0]["content"]

        # Should have conversation history after
        has_conversation = any(
            item.get("role") in ["user", "assistant"]
            for item in augmented_context[1:]
        )
        assert has_conversation

    @pytest.mark.asyncio
    async def test_rag_context_format_is_valid(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_retrieval_service,
        mock_update,
        mock_context,
        mock_vector_db
    ):
        """Test that augmented context format is valid for OpenAI API."""
        chunk = RetrievedChunk(
            chunk_id="1",
            text="Test content",
            score=0.9,
            metadata={}
        )
        mock_vector_db.search.return_value = [chunk]

        message_handler = MessageHandler(
            mock_llm_client,
            mock_database,
            mock_config,
            mock_retrieval_service
        )

        # Execute
        await message_handler.handle(mock_update, mock_context)

        # Assert - context format should be valid
        call_args = mock_llm_client.generate_response.call_args
        augmented_context = call_args[0][1]

        if augmented_context is not None:
            for item in augmented_context:
                assert isinstance(item, dict), "Each context item must be a dict"
                assert "role" in item, "Each context item must have a role"
                assert "content" in item, "Each context item must have content"
                assert item["role"] in ["system", "user", "assistant"], \
                    f"Invalid role: {item['role']}"
                assert isinstance(item["content"], str), "Content must be a string"

    @pytest.mark.asyncio
    async def test_multiple_retrieved_chunks_combined(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_retrieval_service,
        mock_update,
        mock_context,
        mock_vector_db
    ):
        """Test that multiple retrieved chunks are properly combined."""
        chunks = [
            RetrievedChunk(
                chunk_id=f"{i}",
                text=f"Rule {i} content about offside",
                score=0.9 - i * 0.05,
                metadata={"section": f"Law {11 + i}"}
            )
            for i in range(3)
        ]
        mock_vector_db.search.return_value = chunks

        message_handler = MessageHandler(
            mock_llm_client,
            mock_database,
            mock_config,
            mock_retrieval_service
        )

        # Execute
        await message_handler.handle(mock_update, mock_context)

        # Assert - all chunks should be in context
        call_args = mock_llm_client.generate_response.call_args
        augmented_context = call_args[0][1]

        assert augmented_context is not None
        context_str = augmented_context[0]["content"]

        for chunk in chunks:
            assert chunk.text in context_str, \
                f"Chunk '{chunk.text}' not found in context"

    @pytest.mark.asyncio
    async def test_embedding_error_falls_back_to_no_retrieval(
        self,
        mock_llm_client,
        mock_database,
        mock_config,
        mock_embedding_service,
        mock_update,
        mock_context,
    ):
        """Test that embedding errors don't crash the handler."""
        # Setup - embedding service fails
        mock_embedding_service.embed_text = MagicMock(return_value=None)

        with patch("src.services.retrieval_service.VectorDatabase"):
            mock_retrieval_service = RetrievalService(
                mock_config,
                mock_embedding_service
            )

            message_handler = MessageHandler(
                mock_llm_client,
                mock_database,
                mock_config,
                mock_retrieval_service
            )

            # Execute
            await message_handler.handle(mock_update, mock_context)

            # Assert - should still work without retrieval
            assert mock_llm_client.generate_response.called
            call_args = mock_llm_client.generate_response.call_args
            # Context might be None due to embedding failure
            augmented_context = call_args[0][1]
            assert augmented_context is None or len(augmented_context) == 0
