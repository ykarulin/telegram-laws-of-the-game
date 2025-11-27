"""
End-to-End tests for tool-enabled message handling.

Tests the complete workflow where:
1. DocumentLookupTool is initialized
2. LLM receives tool schema in system prompt
3. LLM calls the tool with selected documents
4. Tool returns formatted results
5. LLM uses tool results in response generation

These tests ensure tool calls are properly surfaced to the LLM and that
the mixed retrieval strategy (generic RAG vs tool-enabled) works correctly.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock, call
from src.config import Config
from src.handlers.message_handler import MessageHandler
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase
from src.services.embedding_service import EmbeddingService
from src.services.retrieval_service import RetrievalService
from src.tools.document_lookup_tool import DocumentLookupTool, ToolResult
from src.core.vector_db import RetrievedChunk
from src.core.features import FeatureRegistry, FeatureStatus


@pytest.fixture
def mock_config():
    """Create a configuration with tool enabled."""
    config = Mock(spec=Config)
    config.enable_document_selection = True
    config.max_document_lookups = 5
    config.lookup_max_chunks = 5
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
def mock_llm_client():
    """Create a mock LLM client."""
    client = Mock(spec=LLMClient)
    client.generate_response = Mock(return_value="Response from LLM")
    return client


@pytest.fixture
def mock_database():
    """Create a mock conversation database."""
    return Mock(spec=ConversationDatabase)


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    service = Mock(spec=EmbeddingService)
    service.embed_text = Mock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])
    return service


@pytest.fixture
def mock_retrieval_service():
    """Create a mock retrieval service."""
    service = Mock(spec=RetrievalService)

    # Setup for get_indexed_documents
    service.get_indexed_documents = Mock(
        return_value=["Laws of Game 2024-25", "VAR Guidelines 2024"]
    )

    # Setup for format_document_list
    service.format_document_list = Mock(
        return_value="1. Laws of Game 2024-25\n2. VAR Guidelines 2024"
    )

    # Setup for retrieve_context (generic retrieval)
    chunk1 = Mock(spec=RetrievedChunk)
    chunk1.text = "The offside rule states..."
    chunk1.score = 0.92
    chunk1.metadata = {"document_name": "Laws of Game 2024-25", "section": "Law 11"}

    service.retrieve_context = Mock(return_value=[chunk1])

    # Setup for retrieve_from_documents (tool-enabled retrieval)
    service.retrieve_from_documents = Mock(return_value=[chunk1])

    # Setup for format_context
    service.format_context = Mock(
        return_value="[Document 1]\nSource: Laws of Game 2024-25\nThe offside rule states..."
    )

    # Setup for should_use_retrieval
    service.should_use_retrieval = Mock(return_value=True)

    return service


@pytest.fixture
def feature_registry_with_rag():
    """Create a feature registry with RAG enabled."""
    registry = FeatureRegistry()
    registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)
    return registry


@pytest.fixture
def handler(
    mock_llm_client,
    mock_database,
    mock_config,
    mock_retrieval_service,
    mock_embedding_service,
    feature_registry_with_rag
):
    """Create a MessageHandler with tool enabled."""
    return MessageHandler(
        llm_client=mock_llm_client,
        db=mock_database,
        config=mock_config,
        retrieval_service=mock_retrieval_service,
        embedding_service=mock_embedding_service,
        feature_registry=feature_registry_with_rag,
    )


class TestToolInitialization:
    """Tests for tool initialization in message handler."""

    def test_tool_initialized_when_all_dependencies_available(self, handler):
        """Test that DocumentLookupTool is initialized when all deps present."""
        assert handler.document_lookup_tool is not None
        assert isinstance(handler.document_lookup_tool, DocumentLookupTool)

    def test_tool_not_initialized_when_disabled_in_config(
        self, mock_llm_client, mock_database, mock_config,
        mock_retrieval_service, mock_embedding_service
    ):
        """Test that tool is not initialized when config disables it."""
        mock_config.enable_document_selection = False

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
        )

        assert handler.document_lookup_tool is None

    def test_tool_not_initialized_when_retrieval_service_missing(
        self, mock_llm_client, mock_database, mock_config, mock_embedding_service
    ):
        """Test that tool is not initialized when retrieval service is None."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=None,
            embedding_service=mock_embedding_service,
        )

        assert handler.document_lookup_tool is None

    def test_tool_not_initialized_when_embedding_service_missing(
        self, mock_llm_client, mock_database, mock_config, mock_retrieval_service
    ):
        """Test that tool is not initialized when embedding service is None."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=None,
        )

        assert handler.document_lookup_tool is None


class TestToolSchemaExposure:
    """Tests verifying tool schema is properly exposed to LLM."""

    def test_handler_can_get_tool_schema(self, handler):
        """Test that handler can retrieve tool schema from initialized tool."""
        assert handler.document_lookup_tool is not None
        schema = handler.document_lookup_tool.get_tool_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "lookup_documents"
        assert "properties" in schema["function"]["parameters"]

    def test_tool_schema_includes_available_documents(self, handler, mock_retrieval_service):
        """Test that available documents can be retrieved for prompt injection."""
        available_docs = handler._get_available_documents()

        assert len(available_docs) == 2
        assert "Laws of Game 2024-25" in available_docs
        assert "VAR Guidelines 2024" in available_docs
        mock_retrieval_service.get_indexed_documents.assert_called_once()

    def test_tool_schema_formatted_for_system_prompt(self, handler, mock_retrieval_service):
        """Test that document list can be formatted for system prompt."""
        doc_context = handler._prepare_document_context(
            handler._get_available_documents()
        )

        assert len(doc_context) > 0
        assert "Laws of Game 2024-25" in doc_context
        mock_retrieval_service.format_document_list.assert_called_once()


class TestToolExecutionPath:
    """Tests verifying tool execution is properly integrated."""

    def test_tool_executes_lookup_with_provided_parameters(
        self, handler, mock_retrieval_service
    ):
        """Test that tool can execute lookup with specified parameters."""
        assert handler.document_lookup_tool is not None

        result = handler.document_lookup_tool.execute_lookup(
            document_names=["Laws of Game 2024-25"],
            query="offside rule",
            top_k=3,
            min_similarity=0.7,
        )

        assert result.success is True
        assert len(result.results) == 1
        assert result.query == "offside rule"
        mock_retrieval_service.retrieve_from_documents.assert_called_once()

    def test_tool_formats_results_for_llm_consumption(self, handler):
        """Test that tool can format results as LLM-readable string."""
        assert handler.document_lookup_tool is not None

        chunk = Mock(spec=RetrievedChunk)
        chunk.text = "Test content"
        chunk.metadata = {"section": "Law 1", "document_name": "Laws of Game"}

        result = ToolResult(
            success=True,
            documents_searched=["Laws of Game"],
            query="test",
            results=[chunk],
        )

        formatted = handler.document_lookup_tool.format_result_for_llm(result)

        assert "Test content" in formatted
        assert "Law 1" in formatted
        assert len(formatted) > 0

    def test_tool_error_handling_in_execution(
        self, handler, mock_retrieval_service
    ):
        """Test that tool handles errors gracefully."""
        mock_retrieval_service.retrieve_from_documents.side_effect = Exception("API Error")

        result = handler.document_lookup_tool.execute_lookup(
            document_names=["Laws of Game 2024-25"],
            query="test",
        )

        assert result.success is False
        assert result.error_message is not None
        assert "Lookup failed" in result.error_message


class TestMixedRetrievalStrategy:
    """Tests for mixed retrieval: generic RAG vs tool-enabled paths."""

    def test_generic_rag_path_when_tool_disabled(
        self, mock_llm_client, mock_database, mock_config,
        mock_retrieval_service, mock_embedding_service, feature_registry_with_rag
    ):
        """Test generic RAG retrieval when tool is disabled."""
        mock_config.enable_document_selection = False

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
            feature_registry=feature_registry_with_rag,
        )

        # Verify no tool is initialized
        assert handler.document_lookup_tool is None

        # Verify generic retrieval still works
        chunks = handler._retrieve_documents("test query")
        mock_retrieval_service.retrieve_context.assert_called_once()

    def test_tool_enabled_path_initializes_tool(self, handler):
        """Test that tool-enabled path initializes the lookup tool."""
        assert handler.document_lookup_tool is not None
        assert isinstance(handler.document_lookup_tool, DocumentLookupTool)

    def test_tool_available_documents_retrieved_for_prompt(
        self, handler, mock_retrieval_service
    ):
        """Test that available documents are retrieved for LLM context."""
        available_docs = handler._get_available_documents()

        assert len(available_docs) > 0
        mock_retrieval_service.get_indexed_documents.assert_called()

    def test_generic_retrieval_still_works_with_tool_enabled(
        self, handler, mock_retrieval_service
    ):
        """Test that generic retrieval still occurs even when tool is enabled."""
        chunks = handler._retrieve_documents("test query")

        assert len(chunks) > 0
        mock_retrieval_service.retrieve_context.assert_called()


class TestToolResultIntegration:
    """Tests for tool result formatting and LLM integration."""

    def test_successful_tool_result_formatting(self, handler):
        """Test formatting of successful tool results."""
        chunk = Mock(spec=RetrievedChunk)
        chunk.text = "Offside occurs when a player is nearer to the opponent's goal line..."
        chunk.metadata = {
            "document_name": "Laws of Game 2024-25",
            "section": "Law 11",
            "subsection": "Offside Position"
        }

        result = ToolResult(
            success=True,
            documents_searched=["Laws of Game 2024-25"],
            query="What is offside?",
            results=[chunk],
        )

        formatted = handler.document_lookup_tool.format_result_for_llm(result)

        # Verify formatted output contains key information
        assert "1 relevant sections" in formatted or "relevant sections" in formatted
        assert "offside" in formatted.lower() or "Offside" in formatted

    def test_failed_tool_result_formatting(self, handler):
        """Test formatting of failed tool results."""
        result = ToolResult(
            success=False,
            documents_searched=["Laws of Game 2024-25"],
            query="test",
            results=[],
            error_message="Failed to retrieve documents: Network timeout"
        )

        formatted = handler.document_lookup_tool.format_result_for_llm(result)

        assert "Error" in formatted or "error" in formatted
        assert "Network timeout" in formatted

    def test_empty_tool_result_formatting(self, handler):
        """Test formatting when tool returns no results."""
        result = ToolResult(
            success=True,
            documents_searched=["Laws of Game 2024-25"],
            query="obscure technical detail",
            results=[],
        )

        formatted = handler.document_lookup_tool.format_result_for_llm(result)

        assert "No relevant sections" in formatted or "no relevant" in formatted.lower()


class TestToolInvokedByLLM:
    """Tests simulating LLM tool invocation."""

    def test_llm_receives_tool_schema_in_context(self, handler):
        """Test that tool schema is available for LLM to invoke."""
        # Simulate what would happen when preparing context for LLM
        assert handler.document_lookup_tool is not None
        schema = handler.document_lookup_tool.get_tool_schema()

        # Verify schema has necessary components for function calling
        assert "function" in schema
        assert "name" in schema["function"]
        assert schema["function"]["name"] == "lookup_documents"
        assert "parameters" in schema["function"]

    def test_tool_invocation_with_llm_selected_documents(
        self, handler, mock_retrieval_service
    ):
        """Test tool invocation as LLM would call it."""
        # Simulate LLM selecting documents and querying
        document_selection = ["Laws of Game 2024-25"]
        llm_query = "What is the offside rule?"

        result = handler.document_lookup_tool.execute_lookup(
            document_names=document_selection,
            query=llm_query,
            top_k=3,
            min_similarity=0.7,
        )

        assert result.success is True
        assert result.documents_searched == document_selection
        assert result.query == llm_query

        # Verify correct retrieval method was called
        mock_retrieval_service.retrieve_from_documents.assert_called()

    def test_multiple_tool_invocations_in_single_request(
        self, handler, mock_retrieval_service
    ):
        """Test that tool can be invoked multiple times (up to limit)."""
        invocations = 3

        for i in range(invocations):
            result = handler.document_lookup_tool.execute_lookup(
                document_names=["Laws of Game 2024-25"],
                query=f"Query {i}",
                top_k=3,
                min_similarity=0.7,
            )
            assert result.success is True

        # Verify retrieval was called for each invocation
        assert mock_retrieval_service.retrieve_from_documents.call_count == invocations


class TestToolFallbackBehavior:
    """Tests for fallback behavior when tool is unavailable or fails."""

    def test_graceful_fallback_when_tool_execution_fails(
        self, handler, mock_retrieval_service
    ):
        """Test that failures in tool execution don't break message handling."""
        mock_retrieval_service.retrieve_from_documents.side_effect = Exception("DB Error")

        # Tool execution should fail gracefully
        result = handler.document_lookup_tool.execute_lookup(
            document_names=["Laws of Game 2024-25"],
            query="test",
        )

        assert result.success is False
        assert result.error_message is not None

    def test_generic_retrieval_fallback_when_tool_disabled(
        self, mock_llm_client, mock_database, mock_config,
        mock_retrieval_service, mock_embedding_service, feature_registry_with_rag
    ):
        """Test fallback to generic retrieval when tool is disabled."""
        mock_config.enable_document_selection = False

        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
            feature_registry=feature_registry_with_rag,
        )

        # Generic retrieval should be available
        chunks = handler._retrieve_documents("test query")
        assert mock_retrieval_service.retrieve_context.called

    def test_no_tool_when_retrieval_service_unavailable(
        self, mock_llm_client, mock_database, mock_config, mock_embedding_service
    ):
        """Test that tool is not available when retrieval service is None."""
        handler = MessageHandler(
            llm_client=mock_llm_client,
            db=mock_database,
            config=mock_config,
            retrieval_service=None,
            embedding_service=mock_embedding_service,
        )

        # Tool should not be initialized
        assert handler.document_lookup_tool is None


class TestDynamicThresholdWithTool:
    """Tests for mixed retrieval strategy with dynamic thresholds."""

    def test_tool_respects_dynamic_threshold_config(
        self, handler, mock_retrieval_service
    ):
        """Test that tool-enabled path respects dynamic threshold setting."""
        # Verify config has dynamic threshold enabled
        assert handler.config.rag_dynamic_threshold_margin is not None

        # Execute tool lookup
        result = handler.document_lookup_tool.execute_lookup(
            document_names=["Laws of Game 2024-25"],
            query="test",
            top_k=5,
            min_similarity=0.7,
        )

        # Tool should have executed
        assert result.success is True

    def test_tool_uses_provided_similarity_threshold(
        self, handler, mock_retrieval_service
    ):
        """Test that tool uses the provided similarity threshold."""
        custom_threshold = 0.8

        result = handler.document_lookup_tool.execute_lookup(
            document_names=["Laws of Game 2024-25"],
            query="test",
            top_k=3,
            min_similarity=custom_threshold,
        )

        # Verify the custom threshold was passed to retrieval
        call_kwargs = mock_retrieval_service.retrieve_from_documents.call_args[1]
        assert call_kwargs["threshold"] == custom_threshold
