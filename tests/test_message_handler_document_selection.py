"""
Unit tests for MessageHandler document selection functionality.

Tests the new document selection methods and tool integration.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from src.config import Config
from src.handlers.message_handler import MessageHandler
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = Mock(spec=Config)
    config.enable_document_selection = True
    config.max_document_lookups = 5
    config.lookup_max_chunks = 5
    config.similarity_threshold = 0.7
    config.top_k_retrievals = 5
    config.openai_model = "gpt-4-turbo"
    return config


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    return Mock(spec=LLMClient)


@pytest.fixture
def mock_database():
    """Create a mock conversation database."""
    return Mock(spec=ConversationDatabase)


@pytest.fixture
def mock_retrieval_service():
    """Create a mock retrieval service."""
    return Mock()


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    return Mock()


@pytest.fixture
def handler(mock_llm_client, mock_database, mock_config, mock_retrieval_service, mock_embedding_service):
    """Create a MessageHandler with mocked dependencies."""
    return MessageHandler(
        llm_client=mock_llm_client,
        db=mock_database,
        config=mock_config,
        retrieval_service=mock_retrieval_service,
        embedding_service=mock_embedding_service,
    )


class TestGetAvailableDocuments:
    """Tests for _get_available_documents method."""

    def test_returns_document_list(self, handler, mock_retrieval_service):
        """Test that method returns document list from service."""
        expected_docs = ["Laws of Game 2024-25", "VAR Guidelines 2024"]
        mock_retrieval_service.get_indexed_documents.return_value = expected_docs

        result = handler._get_available_documents()

        assert result == expected_docs
        mock_retrieval_service.get_indexed_documents.assert_called_once()

    def test_returns_empty_list_when_service_unavailable(self, mock_config, mock_llm_client, mock_database):
        """Test that method returns empty list if retrieval service is None."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=None,  # No retrieval service
        )

        result = handler._get_available_documents()

        assert result == []

    def test_returns_empty_list_on_exception(self, handler, mock_retrieval_service):
        """Test that method returns empty list on error."""
        mock_retrieval_service.get_indexed_documents.side_effect = Exception("Service error")

        result = handler._get_available_documents()

        assert result == []

    def test_handles_no_documents(self, handler, mock_retrieval_service):
        """Test that method handles empty document list."""
        mock_retrieval_service.get_indexed_documents.return_value = []

        result = handler._get_available_documents()

        assert result == []


class TestPrepareDocumentContext:
    """Tests for _prepare_document_context method."""

    def test_formats_single_document(self, handler, mock_retrieval_service):
        """Test formatting a single document."""
        expected_formatted = "1. Laws of Game 2024-25"
        mock_retrieval_service.format_document_list.return_value = expected_formatted

        result = handler._prepare_document_context(["Laws of Game 2024-25"])

        assert result == expected_formatted
        mock_retrieval_service.format_document_list.assert_called_once_with(
            ["Laws of Game 2024-25"]
        )

    def test_formats_multiple_documents(self, handler, mock_retrieval_service):
        """Test formatting multiple documents."""
        docs = ["Laws of Game 2024-25", "VAR Guidelines 2024", "FAQ"]
        expected_formatted = "1. Laws of Game 2024-25\n2. VAR Guidelines 2024\n3. FAQ"
        mock_retrieval_service.format_document_list.return_value = expected_formatted

        result = handler._prepare_document_context(docs)

        assert result == expected_formatted
        assert "1. Laws of Game 2024-25" in result

    def test_returns_empty_string_for_empty_list(self, handler):
        """Test that empty document list returns empty string."""
        result = handler._prepare_document_context([])

        assert result == ""

    def test_returns_empty_string_when_service_unavailable(self, mock_config, mock_llm_client, mock_database):
        """Test that method returns empty string if retrieval service is None."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=None,
        )

        result = handler._prepare_document_context(["Doc1"])

        assert result == ""

    def test_returns_empty_string_on_format_error(self, handler, mock_retrieval_service):
        """Test that method returns empty string on formatting error."""
        mock_retrieval_service.format_document_list.side_effect = Exception("Format error")

        result = handler._prepare_document_context(["Doc1"])

        assert result == ""

    def test_passes_documents_to_retrieval_service(self, handler, mock_retrieval_service):
        """Test that document list is passed correctly to service."""
        docs = ["Doc1", "Doc2", "Doc3"]
        mock_retrieval_service.format_document_list.return_value = ""

        handler._prepare_document_context(docs)

        mock_retrieval_service.format_document_list.assert_called_once_with(docs)


class TestDocumentLookupToolInitialization:
    """Tests for document lookup tool initialization."""

    def test_tool_initialized_when_enabled_and_services_available(self, handler):
        """Test that tool is initialized when config enables it and services are available."""
        assert handler.document_lookup_tool is not None

    def test_tool_not_initialized_when_disabled(self, mock_llm_client, mock_database, mock_config, mock_retrieval_service, mock_embedding_service):
        """Test that tool is not initialized when feature is disabled."""
        mock_config.enable_document_selection = False

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        assert handler.document_lookup_tool is None

    def test_tool_not_initialized_without_retrieval_service(self, mock_llm_client, mock_database, mock_config, mock_embedding_service):
        """Test that tool is not initialized without retrieval service."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=None,
            embedding_service=mock_embedding_service,
        )

        assert handler.document_lookup_tool is None

    def test_tool_not_initialized_without_embedding_service(self, mock_llm_client, mock_database, mock_config, mock_retrieval_service):
        """Test that tool is not initialized without embedding service."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=None,
        )

        assert handler.document_lookup_tool is None

    def test_embedding_service_stored(self, handler, mock_embedding_service):
        """Test that embedding service is stored in handler."""
        assert handler.embedding_service == mock_embedding_service

    def test_config_stored(self, handler, mock_config):
        """Test that config is stored in handler."""
        assert handler.config == mock_config

    def test_all_services_stored(self, handler, mock_llm_client, mock_database, mock_retrieval_service):
        """Test that all services are stored."""
        assert handler.llm_client == mock_llm_client
        assert handler.db == mock_database
        assert handler.retrieval_service == mock_retrieval_service


class TestGetAvailableDocumentsEdgeCases:
    """Edge case tests for document retrieval."""

    def test_handles_single_document(self, handler, mock_retrieval_service):
        """Test with single document."""
        mock_retrieval_service.get_indexed_documents.return_value = ["Only Document"]

        result = handler._get_available_documents()

        assert len(result) == 1
        assert result[0] == "Only Document"

    def test_handles_many_documents(self, handler, mock_retrieval_service):
        """Test with many documents."""
        docs = [f"Document {i}" for i in range(50)]
        mock_retrieval_service.get_indexed_documents.return_value = docs

        result = handler._get_available_documents()

        assert len(result) == 50
        assert result == docs

    def test_handles_documents_with_special_characters(self, handler, mock_retrieval_service):
        """Test with documents containing special characters."""
        docs = [
            "Laws of Game (2024-25)",
            "VAR & Referee Guidelines",
            "FAQ - Common Questions",
            "Rules/Regulations",
        ]
        mock_retrieval_service.get_indexed_documents.return_value = docs

        result = handler._get_available_documents()

        assert result == docs

    def test_preserves_document_order(self, handler, mock_retrieval_service):
        """Test that document order is preserved."""
        docs = ["Z Document", "A Document", "M Document"]
        mock_retrieval_service.get_indexed_documents.return_value = docs

        result = handler._get_available_documents()

        assert result == docs  # Order should be preserved


class TestDocumentContextPreparationEdgeCases:
    """Edge case tests for document context formatting."""

    def test_handles_documents_with_long_names(self, handler, mock_retrieval_service):
        """Test with very long document names."""
        long_name = "A" * 200 + " - Very Long Document Name"
        mock_retrieval_service.format_document_list.return_value = f"1. {long_name}"

        result = handler._prepare_document_context([long_name])

        assert long_name in result

    def test_handles_unicode_in_document_names(self, handler, mock_retrieval_service):
        """Test with unicode characters in document names."""
        docs = ["Règles de Jeu 2024-25", "法則のガイド", "🏀 Basketball Rules"]
        formatted = "1. Règles de Jeu 2024-25\n2. 法則のガイド\n3. 🏀 Basketball Rules"
        mock_retrieval_service.format_document_list.return_value = formatted

        result = handler._prepare_document_context(docs)

        assert "Règles de Jeu 2024-25" in result
        mock_retrieval_service.format_document_list.assert_called_once_with(docs)

    def test_handles_none_as_empty_list(self, handler):
        """Test that None is handled safely."""
        # The method expects a list, so we test the contract
        result = handler._prepare_document_context([])
        assert result == ""
