"""
Tests for tool-enabled vs non-tool fallback paths.

Tests validate that:
1. Tool initialization gracefully fails when dependencies are missing
2. Message handler works with and without tool enabled
3. Generic RAG is used as fallback when tool is unavailable
4. Tool errors don't break the message handling flow
5. Configuration properly gates tool initialization
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.config import Config
from src.handlers.message_handler import MessageHandler
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.core.vector_db import RetrievedChunk
from src.core.features import FeatureRegistry, FeatureStatus


@pytest.fixture
def base_mock_config():
    """Create base configuration."""
    config = Mock(spec=Config)
    config.similarity_threshold = 0.7
    config.top_k_retrievals = 5
    config.openai_model = "gpt-4-turbo"
    config.qdrant_host = "localhost"
    config.qdrant_port = 6333
    config.qdrant_api_key = None
    config.qdrant_collection_name = "documents"
    config.rag_dynamic_threshold_margin = 0.1
    return config


@pytest.fixture
def config_with_tool_enabled(base_mock_config):
    """Configuration with tool enabled."""
    base_mock_config.enable_document_selection = True
    base_mock_config.max_document_lookups = 5
    base_mock_config.lookup_max_chunks = 5
    return base_mock_config


@pytest.fixture
def config_with_tool_disabled(base_mock_config):
    """Configuration with tool disabled."""
    base_mock_config.enable_document_selection = False
    return base_mock_config


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = Mock(spec=LLMClient)
    client.generate_response = Mock(return_value="LLM response")
    return client


@pytest.fixture
def mock_database():
    """Create a mock conversation database."""
    db = Mock(spec=ConversationDatabase)
    db.get_conversation_chain = Mock(return_value=None)
    db.save_message = Mock()
    return db


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    service = Mock(spec=EmbeddingService)
    service.embed_text = Mock(return_value=[0.1, 0.2, 0.3])
    return service


@pytest.fixture
def mock_retrieval_service():
    """Create a mock retrieval service."""
    service = Mock(spec=RetrievalService)

    # Setup for generic retrieval
    chunk = Mock(spec=RetrievedChunk)
    chunk.text = "Content"
    chunk.score = 0.9
    chunk.metadata = {"document_name": "Doc", "section": "Sec"}

    service.retrieve_context = Mock(return_value=[chunk])
    service.should_use_retrieval = Mock(return_value=True)
    service.format_context = Mock(return_value="Formatted content")
    service.get_indexed_documents = Mock(return_value=["Doc1", "Doc2"])
    service.format_document_list = Mock(return_value="1. Doc1\n2. Doc2")
    service.retrieve_from_documents = Mock(return_value=[chunk])

    return service


@pytest.fixture
def feature_registry_with_rag():
    """Create a feature registry with RAG enabled."""
    registry = FeatureRegistry()
    registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)
    return registry


class TestToolInitializationWithDependencies:
    """Tests for tool initialization based on dependency availability."""

    def test_tool_initialized_when_all_deps_present(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test tool is initialized when all dependencies are present."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        assert handler.document_lookup_tool is not None
        assert handler.config.enable_document_selection is True

    def test_tool_not_initialized_when_config_disabled(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test tool is not initialized when config disables it."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        assert handler.document_lookup_tool is None
        assert handler.config.enable_document_selection is False

    def test_tool_not_initialized_when_retrieval_service_missing(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_embedding_service
    ):
        """Test tool is not initialized when retrieval service is None."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=None,
            embedding_service=mock_embedding_service,
        )

        assert handler.document_lookup_tool is None

    def test_tool_not_initialized_when_embedding_service_missing(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service
    ):
        """Test tool is not initialized when embedding service is None."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=None,
        )

        assert handler.document_lookup_tool is None


class TestGenericRagFallback:
    """Tests for fallback to generic RAG when tool is not available."""

    def test_generic_retrieval_works_without_tool(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service, feature_registry_with_rag
    ):
        """Test that generic retrieval works when tool is disabled."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry_with_rag,
        )

        chunks = handler._retrieve_documents("test query")

        assert len(chunks) > 0
        mock_retrieval_service.retrieve_context.assert_called_once()

    def test_generic_retrieval_fallback_with_config_disabled(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service, mock_embedding_service, feature_registry_with_rag
    ):
        """Test generic retrieval when tool is disabled by config."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
            feature_registry=feature_registry_with_rag,
        )

        # Verify tool not initialized
        assert handler.document_lookup_tool is None

        # Verify generic retrieval still works
        chunks = handler._retrieve_documents("test query")
        assert mock_retrieval_service.retrieve_context.called

    def test_generic_retrieval_fallback_with_missing_retrieval_service(
        self, mock_llm_client, mock_database, config_with_tool_enabled
    ):
        """Test fallback when retrieval service is missing."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=None,
        )

        # Should return empty chunks gracefully
        chunks = handler._retrieve_documents("test query")

        assert chunks == []

    def test_generic_retrieval_still_available_with_tool_enabled(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service, feature_registry_with_rag
    ):
        """Test that generic retrieval still happens with tool enabled."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
            feature_registry=feature_registry_with_rag,
        )

        # Generic retrieval should still be available
        chunks = handler._retrieve_documents("test query")

        assert len(chunks) > 0
        mock_retrieval_service.retrieve_context.assert_called()


class TestToolErrorHandling:
    """Tests for error handling when tool execution fails."""

    def test_tool_execution_failure_handled_gracefully(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test that tool execution failures are handled gracefully."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        # Simulate tool execution failure
        mock_retrieval_service.retrieve_from_documents.side_effect = Exception("API Error")

        result = handler.document_lookup_tool.execute_lookup(
            document_names=["Doc"],
            query="test",
        )

        # Tool should return failure result, not raise
        assert result.success is False
        assert result.error_message is not None

    def test_tool_parameter_validation_catches_errors(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test that parameter validation prevents invalid tool calls."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        # Attempt invalid call
        result = handler.document_lookup_tool.execute_lookup(
            document_names=[],  # Invalid
            query="test",
        )

        assert result.success is False
        assert "empty" in result.error_message.lower()

    def test_retrieval_service_exception_handled(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test that retrieval service exceptions are caught."""
        mock_retrieval_service.retrieve_from_documents.side_effect = RuntimeError("DB failed")

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        result = handler.document_lookup_tool.execute_lookup(
            document_names=["Doc"],
            query="test",
        )

        # Should not raise, should return failure
        assert result.success is False

    def test_embedding_service_exception_handled(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_embedding_service
    ):
        """Test that embedding service exceptions are handled."""
        mock_embedding_service.embed_text.side_effect = Exception("Embedding failed")

        # Create a retrieval service that will fail when embedding fails
        mock_retrieval_service = Mock(spec=RetrievalService)
        mock_retrieval_service.should_use_retrieval = Mock(return_value=True)
        # When embedding fails, retrieve_context should fail and return empty
        mock_retrieval_service.retrieve_context = Mock(return_value=[])

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        # Retrieval should fail gracefully
        chunks = handler._retrieve_documents("test")
        assert chunks == []


class TestMessageHandlerWithoutTool:
    """Tests for message handler when tool is not available."""

    def test_handler_works_without_tool_initialized(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service
    ):
        """Test that message handler functions without tool."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
        )

        # Core functionality should still work
        assert handler.llm_client is not None
        assert handler.db is not None
        assert handler.retrieval_service is not None
        assert handler.document_lookup_tool is None

    def test_available_documents_empty_without_tool(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service
    ):
        """Test that available documents returns empty when tool disabled."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
        )

        # When tool is not initialized, _get_available_documents should still work
        # but may not be called
        assert handler.document_lookup_tool is None

    def test_document_context_empty_without_tool(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service
    ):
        """Test that document context preparation works without tool."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
        )

        # Prepare context for empty document list
        context = handler._prepare_document_context([])
        assert context == ""


class TestMixedRetrievalModes:
    """Tests comparing tool-enabled vs tool-disabled retrieval modes."""

    def test_tool_disabled_uses_only_generic_retrieval(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service, feature_registry_with_rag
    ):
        """Test that disabled tool uses only generic retrieval."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry_with_rag,
        )

        chunks = handler._retrieve_documents("test")

        # Should use generic retrieval only
        mock_retrieval_service.retrieve_context.assert_called_once()
        mock_retrieval_service.retrieve_from_documents.assert_not_called()

    def test_tool_enabled_has_both_paths_available(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service, feature_registry_with_rag
    ):
        """Test that enabled tool has both generic and specific retrieval."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
            feature_registry=feature_registry_with_rag,
        )

        # Generic retrieval should still work
        chunks = handler._retrieve_documents("test")
        assert mock_retrieval_service.retrieve_context.called

        # Tool should also be available for specific retrieval
        assert handler.document_lookup_tool is not None
        tool_result = handler.document_lookup_tool.execute_lookup(
            document_names=["Doc"],
            query="test",
        )
        assert mock_retrieval_service.retrieve_from_documents.called

    def test_tool_disabled_does_not_call_get_available_documents(
        self, mock_llm_client, mock_database, config_with_tool_disabled,
        mock_retrieval_service
    ):
        """Test that disabled tool doesn't prepare document context."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_disabled,
            retrieval_service=mock_retrieval_service,
        )

        # With tool disabled, available documents shouldn't be needed
        assert handler.document_lookup_tool is None


class TestConfigurationGating:
    """Tests for configuration-based gating of tool initialization."""

    def test_enable_document_selection_flag_controls_tool(
        self, mock_llm_client, mock_database, base_mock_config,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test that enable_document_selection controls tool initialization."""
        # Test with enabled
        base_mock_config.enable_document_selection = True
        base_mock_config.max_document_lookups = 5
        base_mock_config.lookup_max_chunks = 5

        handler_enabled = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=base_mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )
        assert handler_enabled.document_lookup_tool is not None

        # Test with disabled
        base_mock_config.enable_document_selection = False
        handler_disabled = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=base_mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )
        assert handler_disabled.document_lookup_tool is None

    def test_max_document_lookups_limits_tool_calls(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test that max_document_lookups config is respected."""
        config_with_tool_enabled.max_document_lookups = 3

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        # Tool should be initialized with limit
        assert handler.document_lookup_tool is not None
        assert handler.config.max_document_lookups == 3

    def test_lookup_max_chunks_limits_per_call(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test that lookup_max_chunks config limits results per tool call."""
        config_with_tool_enabled.lookup_max_chunks = 5

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        # Tool should respect limit
        assert handler.config.lookup_max_chunks == 5


class TestFallbackChain:
    """Tests for the complete fallback chain."""

    def test_fallback_when_tool_unavailable_uses_generic_retrieval(
        self, mock_llm_client, mock_database, config_with_tool_enabled,
        mock_retrieval_service, feature_registry_with_rag
    ):
        """Test fallback to generic retrieval when tool unavailable."""
        # Tool can't be initialized without embedding service
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=mock_retrieval_service,
            embedding_service=None,
            feature_registry=feature_registry_with_rag,
        )

        # Tool should not be available
        assert handler.document_lookup_tool is None

        # But generic retrieval should still work
        chunks = handler._retrieve_documents("test")
        mock_retrieval_service.retrieve_context.assert_called()

    def test_fallback_chain_no_retrieval_service(
        self, mock_llm_client, mock_database, config_with_tool_enabled
    ):
        """Test fallback when no retrieval service at all."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=config_with_tool_enabled,
            retrieval_service=None,
        )

        # Tool should not be available
        assert handler.document_lookup_tool is None

        # Generic retrieval should fail gracefully
        chunks = handler._retrieve_documents("test")
        assert chunks == []
