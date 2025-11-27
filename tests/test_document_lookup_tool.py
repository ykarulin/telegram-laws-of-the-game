"""
Unit tests for DocumentLookupTool.

Tests schema validation, parameter validation, and tool execution logic.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.config import Config, Environment
from src.tools.document_lookup_tool import DocumentLookupTool, ToolResult
from src.core.vector_db import RetrievedChunk


@pytest.fixture
def mock_config():
    """Create a mock configuration object."""
    config = Mock(spec=Config)
    config.similarity_threshold = 0.7
    config.lookup_max_chunks = 5
    config.max_document_lookups = 5
    return config


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    return Mock()


@pytest.fixture
def mock_retrieval_service():
    """Create a mock retrieval service."""
    return Mock()


@pytest.fixture
def tool(mock_config, mock_embedding_service, mock_retrieval_service):
    """Create a DocumentLookupTool instance for testing."""
    return DocumentLookupTool(
        config=mock_config,
        embedding_service=mock_embedding_service,
        retrieval_service=mock_retrieval_service,
        available_documents=["Laws of Game 2024-25", "VAR Guidelines 2024"],
    )


class TestToolSchema:
    """Tests for tool schema generation."""

    def test_get_tool_schema_returns_valid_structure(self, tool):
        """Test that schema has correct overall structure."""
        schema = tool.get_tool_schema()

        assert "type" in schema
        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]

    def test_schema_has_correct_name(self, tool):
        """Test that tool schema has correct name."""
        schema = tool.get_tool_schema()
        assert schema["function"]["name"] == "lookup_documents"

    def test_schema_has_description(self, tool):
        """Test that tool schema has description."""
        schema = tool.get_tool_schema()
        assert len(schema["function"]["description"]) > 0
        assert "football" in schema["function"]["description"].lower()

    def test_schema_parameters_structure(self, tool):
        """Test that parameters have correct structure."""
        schema = tool.get_tool_schema()
        params = schema["function"]["parameters"]

        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params
        assert set(params["required"]) == {"document_names", "query"}

    def test_schema_has_all_properties(self, tool):
        """Test that all required properties are in schema."""
        schema = tool.get_tool_schema()
        props = schema["function"]["parameters"]["properties"]

        assert "document_names" in props
        assert "query" in props
        assert "top_k" in props
        assert "min_similarity" in props

    def test_document_names_property_structure(self, tool):
        """Test document_names property definition."""
        schema = tool.get_tool_schema()
        doc_names = schema["function"]["parameters"]["properties"]["document_names"]

        assert doc_names["type"] == "array"
        assert doc_names["items"]["type"] == "string"
        assert doc_names["minItems"] == 1

    def test_query_property_structure(self, tool):
        """Test query property definition."""
        schema = tool.get_tool_schema()
        query = schema["function"]["parameters"]["properties"]["query"]

        assert query["type"] == "string"
        assert query["minLength"] == 1

    def test_top_k_property_constraints(self, tool, mock_config):
        """Test top_k property has correct constraints."""
        schema = tool.get_tool_schema()
        top_k = schema["function"]["parameters"]["properties"]["top_k"]

        assert top_k["type"] == "integer"
        assert top_k["minimum"] == 1
        assert top_k["maximum"] == mock_config.lookup_max_chunks
        assert top_k["default"] == 3

    def test_min_similarity_property_constraints(self, tool, mock_config):
        """Test min_similarity property has correct constraints."""
        schema = tool.get_tool_schema()
        similarity = schema["function"]["parameters"]["properties"]["min_similarity"]

        assert similarity["type"] == "number"
        assert similarity["minimum"] == 0.0
        assert similarity["maximum"] == 1.0
        assert similarity["default"] == mock_config.similarity_threshold


class TestParameterValidation:
    """Tests for parameter validation."""

    def test_valid_parameters_return_none(self, tool):
        """Test that valid parameters pass validation."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="offside rule",
            top_k=3,
            min_similarity=0.7,
        )
        assert error is None

    def test_empty_document_names_fails(self, tool):
        """Test that empty document_names list fails validation."""
        error = tool._validate_parameters(
            document_names=[],
            query="offside rule",
            top_k=3,
            min_similarity=0.7,
        )
        assert error is not None
        assert "document_names cannot be empty" in error

    def test_non_list_document_names_fails(self, tool):
        """Test that non-list document_names fails validation."""
        error = tool._validate_parameters(
            document_names="Laws of Game 2024-25",
            query="offside rule",
            top_k=3,
            min_similarity=0.7,
        )
        assert error is not None
        assert "document_names must be a list" in error

    def test_too_many_documents_fails(self, tool):
        """Test that more than 10 documents fails validation."""
        error = tool._validate_parameters(
            document_names=[f"Doc {i}" for i in range(11)],
            query="test",
            top_k=3,
            min_similarity=0.7,
        )
        assert error is not None
        assert "more than 10 documents" in error

    def test_empty_query_fails(self, tool):
        """Test that empty query fails validation."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="",
            top_k=3,
            min_similarity=0.7,
        )
        assert error is not None
        assert "query cannot be empty" in error

    def test_whitespace_only_query_fails(self, tool):
        """Test that whitespace-only query fails validation."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="   ",
            top_k=3,
            min_similarity=0.7,
        )
        assert error is not None
        assert "query cannot be empty" in error

    def test_very_long_query_fails(self, tool):
        """Test that query longer than 500 chars fails."""
        long_query = "a" * 501
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query=long_query,
            top_k=3,
            min_similarity=0.7,
        )
        assert error is not None
        assert "query is too long" in error

    def test_non_integer_top_k_fails(self, tool):
        """Test that non-integer top_k fails validation."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="offside",
            top_k=3.5,
            min_similarity=0.7,
        )
        assert error is not None
        assert "top_k must be an integer" in error

    def test_zero_top_k_fails(self, tool):
        """Test that top_k=0 fails validation."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="offside",
            top_k=0,
            min_similarity=0.7,
        )
        assert error is not None
        assert "top_k must be at least 1" in error

    def test_top_k_exceeds_max_fails(self, tool, mock_config):
        """Test that top_k exceeding maximum fails."""
        mock_config.lookup_max_chunks = 5
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="offside",
            top_k=6,
            min_similarity=0.7,
        )
        assert error is not None
        assert "cannot exceed" in error

    def test_non_numeric_similarity_fails(self, tool):
        """Test that non-numeric min_similarity fails."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="offside",
            top_k=3,
            min_similarity="high",
        )
        assert error is not None
        assert "min_similarity must be a number" in error

    def test_similarity_below_zero_fails(self, tool):
        """Test that min_similarity < 0 fails."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="offside",
            top_k=3,
            min_similarity=-0.1,
        )
        assert error is not None
        assert "between 0.0 and 1.0" in error

    def test_similarity_above_one_fails(self, tool):
        """Test that min_similarity > 1.0 fails."""
        error = tool._validate_parameters(
            document_names=["Laws of Game 2024-25"],
            query="offside",
            top_k=3,
            min_similarity=1.1,
        )
        assert error is not None
        assert "between 0.0 and 1.0" in error

    def test_boundary_valid_parameters(self, tool):
        """Test that boundary values pass validation."""
        # Min values
        error = tool._validate_parameters(
            document_names=["Doc"],
            query="q",
            top_k=1,
            min_similarity=0.0,
        )
        assert error is None

        # Max values
        error = tool._validate_parameters(
            document_names=[f"Doc {i}" for i in range(10)],
            query="q" * 500,
            top_k=5,
            min_similarity=1.0,
        )
        assert error is None


class TestExecuteLookup:
    """Tests for execute_lookup method."""

    def test_successful_lookup_returns_success(self, tool, mock_retrieval_service):
        """Test that successful lookup returns success result."""
        mock_chunk = Mock(spec=RetrievedChunk)
        mock_retrieval_service.retrieve_from_documents.return_value = [mock_chunk]

        result = tool.execute_lookup(
            document_names=["Laws of Game 2024-25"],
            query="offside",
            top_k=3,
            min_similarity=0.7,
        )

        assert result.success is True
        assert len(result.results) == 1
        assert result.error_message is None

    def test_lookup_uses_provided_parameters(self, tool, mock_retrieval_service):
        """Test that lookup uses provided parameters correctly."""
        mock_retrieval_service.retrieve_from_documents.return_value = []

        tool.execute_lookup(
            document_names=["Doc1", "Doc2"],
            query="test query",
            top_k=4,
            min_similarity=0.8,
        )

        mock_retrieval_service.retrieve_from_documents.assert_called_once()
        call_kwargs = mock_retrieval_service.retrieve_from_documents.call_args[1]
        assert call_kwargs["document_names"] == ["Doc1", "Doc2"]
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["top_k"] == 4
        assert call_kwargs["threshold"] == 0.8

    def test_lookup_uses_defaults_for_missing_parameters(self, tool, mock_retrieval_service, mock_config):
        """Test that lookup uses config defaults for missing parameters."""
        mock_config.similarity_threshold = 0.7
        mock_retrieval_service.retrieve_from_documents.return_value = []

        tool.execute_lookup(
            document_names=["Doc"],
            query="test",
        )

        call_kwargs = mock_retrieval_service.retrieve_from_documents.call_args[1]
        assert call_kwargs["top_k"] == 3
        assert call_kwargs["threshold"] == 0.7

    def test_invalid_parameters_return_failure(self, tool):
        """Test that invalid parameters return failure result."""
        result = tool.execute_lookup(
            document_names=[],
            query="test",
        )

        assert result.success is False
        assert result.error_message is not None
        assert "empty" in result.error_message

    def test_retrieval_service_exception_returns_failure(self, tool, mock_retrieval_service):
        """Test that retrieval service exceptions are caught."""
        mock_retrieval_service.retrieve_from_documents.side_effect = Exception("API Error")

        result = tool.execute_lookup(
            document_names=["Doc"],
            query="test",
        )

        assert result.success is False
        assert result.error_message is not None
        assert "Lookup failed" in result.error_message

    def test_empty_results_returns_success(self, tool, mock_retrieval_service):
        """Test that empty results still return success."""
        mock_retrieval_service.retrieve_from_documents.return_value = []

        result = tool.execute_lookup(
            document_names=["Doc"],
            query="test",
        )

        assert result.success is True
        assert len(result.results) == 0

    def test_result_contains_searched_documents(self, tool, mock_retrieval_service):
        """Test that result includes which documents were searched."""
        mock_retrieval_service.retrieve_from_documents.return_value = []
        doc_names = ["Doc1", "Doc2"]

        result = tool.execute_lookup(
            document_names=doc_names,
            query="test",
        )

        assert result.documents_searched == doc_names

    def test_result_contains_query(self, tool, mock_retrieval_service):
        """Test that result includes the original query."""
        mock_retrieval_service.retrieve_from_documents.return_value = []
        query = "test query"

        result = tool.execute_lookup(
            document_names=["Doc"],
            query=query,
        )

        assert result.query == query


class TestFormatResultForLlm:
    """Tests for formatting results for LLM consumption."""

    def test_format_error_result(self, tool):
        """Test formatting an error result."""
        result = ToolResult(
            success=False,
            documents_searched=["Doc"],
            query="test",
            results=[],
            error_message="Test error",
        )

        formatted = tool.format_result_for_llm(result)
        assert "Error" in formatted
        assert "Test error" in formatted

    def test_format_empty_results(self, tool):
        """Test formatting result with no matches."""
        result = ToolResult(
            success=True,
            documents_searched=["Laws of Game 2024-25"],
            query="test",
            results=[],
        )

        formatted = tool.format_result_for_llm(result)
        assert "No relevant sections found" in formatted
        assert "Laws of Game 2024-25" in formatted
        assert "test" in formatted

    def test_format_with_results(self, tool):
        """Test formatting result with chunks."""
        chunk = Mock(spec=RetrievedChunk)
        chunk.text = "Test content"
        chunk.metadata = {"section": "Law 1"}

        result = ToolResult(
            success=True,
            documents_searched=["Doc"],
            query="test",
            results=[chunk],
        )

        formatted = tool.format_result_for_llm(result)
        assert "1 relevant sections" in formatted
        assert "Test content" in formatted
        assert "Law 1" in formatted

    def test_format_multiple_results(self, tool):
        """Test formatting multiple results."""
        chunks = []
        for i in range(3):
            chunk = Mock(spec=RetrievedChunk)
            chunk.text = f"Content {i}"
            chunk.metadata = {"section": f"Section {i}"}
            chunks.append(chunk)

        result = ToolResult(
            success=True,
            documents_searched=["Doc"],
            query="test",
            results=chunks,
        )

        formatted = tool.format_result_for_llm(result)
        assert "3 relevant sections" in formatted
        for i in range(3):
            assert f"Content {i}" in formatted
