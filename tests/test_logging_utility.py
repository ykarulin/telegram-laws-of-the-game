"""Tests for logging utility functions."""
import logging
import pytest
from unittest.mock import Mock, patch, call
from src.utils.logging import (
    debug_log_rag_retrieval,
    debug_log_llm_context,
    debug_log_llm_response,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    return Mock(spec=logging.Logger)


class TestDebugLogRagRetrieval:
    """Test debug_log_rag_retrieval function."""

    def test_logs_nothing_when_level_above_debug(self, mock_logger):
        """Should not log when logger level is above DEBUG."""
        mock_logger.level = logging.INFO

        chunk_mock = Mock()
        debug_log_rag_retrieval(mock_logger, [chunk_mock])

        mock_logger.debug.assert_not_called()

    def test_logs_when_level_is_debug(self, mock_logger):
        """Should log when logger level is DEBUG."""
        mock_logger.level = logging.DEBUG

        chunk_mock = Mock()
        chunk_mock.score = 0.95
        chunk_mock.metadata = {"document_name": "test.pdf"}
        chunk_mock.text = "This is test content for debugging"

        debug_log_rag_retrieval(mock_logger, [chunk_mock])

        # Should have logged the header
        assert mock_logger.debug.called
        calls = mock_logger.debug.call_args_list
        assert any("RAG RETRIEVAL DETAILS" in str(call) for call in calls)

    def test_logs_chunk_details(self, mock_logger):
        """Should log score and metadata for each chunk."""
        mock_logger.level = logging.DEBUG

        chunk = Mock()
        chunk.score = 0.87
        chunk.metadata = {
            "document_name": "rules.pdf",
            "document_type": "pdf",
            "section": "Offside Rule"
        }
        chunk.text = "The player is in an offside position..."

        debug_log_rag_retrieval(mock_logger, [chunk])

        calls = [str(call) for call in mock_logger.debug.call_args_list]
        # Verify score is logged
        assert any("0.870" in call for call in calls)

    def test_handles_empty_metadata(self, mock_logger):
        """Should handle chunks with empty or missing metadata."""
        mock_logger.level = logging.DEBUG

        chunk = Mock()
        chunk.score = 0.92
        chunk.metadata = None
        chunk.text = "Test content"

        debug_log_rag_retrieval(mock_logger, [chunk])

        assert mock_logger.debug.called

    def test_handles_multiple_chunks(self, mock_logger):
        """Should log details for all chunks."""
        mock_logger.level = logging.DEBUG

        chunks = [
            Mock(score=0.95, metadata={"document_name": "doc1.pdf"}, text="Content 1"),
            Mock(score=0.87, metadata={"document_name": "doc2.pdf"}, text="Content 2"),
            Mock(score=0.76, metadata={"document_name": "doc3.pdf"}, text="Content 3"),
        ]

        debug_log_rag_retrieval(mock_logger, chunks)

        assert mock_logger.debug.call_count >= 3  # At least one call per chunk


class TestDebugLogLlmContext:
    """Test debug_log_llm_context function."""

    def test_logs_nothing_when_level_above_debug(self, mock_logger):
        """Should not log when logger level is above DEBUG."""
        mock_logger.level = logging.INFO

        debug_log_llm_context(mock_logger, "What is offside?")

        mock_logger.debug.assert_not_called()

    def test_logs_when_level_is_debug(self, mock_logger):
        """Should log when logger level is DEBUG."""
        mock_logger.level = logging.DEBUG

        debug_log_llm_context(mock_logger, "What is offside?")

        assert mock_logger.debug.called
        calls = [str(call) for call in mock_logger.debug.call_args_list]
        assert any("SENDING TO LLM" in call for call in calls)

    def test_logs_user_query(self, mock_logger):
        """Should log the user query."""
        mock_logger.level = logging.DEBUG

        query = "Explain the handball rule"
        debug_log_llm_context(mock_logger, query)

        calls = [str(call) for call in mock_logger.debug.call_args_list]
        assert any("Explain the handball rule" in call for call in calls)

    def test_logs_rag_context_when_provided(self, mock_logger):
        """Should log RAG context info when provided."""
        mock_logger.level = logging.DEBUG

        debug_log_llm_context(
            mock_logger,
            "What is offside?",
            retrieved_context="In soccer, offside occurs when...",
            retrieved_chunks_count=2,
            conversation_context_count=0
        )

        calls = [str(call) for call in mock_logger.debug.call_args_list]
        # Should mention RAG context
        assert any("RAG" in call for call in calls)

    def test_logs_conversation_context_when_provided(self, mock_logger):
        """Should log conversation context info when provided."""
        mock_logger.level = logging.DEBUG

        debug_log_llm_context(
            mock_logger,
            "What about handball?",
            retrieved_context=None,
            retrieved_chunks_count=0,
            conversation_context_count=3
        )

        calls = [str(call) for call in mock_logger.debug.call_args_list]
        # Should mention conversation context
        assert any("Conversation" in call for call in calls)

    def test_logs_both_contexts(self, mock_logger):
        """Should log both RAG and conversation context when present."""
        mock_logger.level = logging.DEBUG

        debug_log_llm_context(
            mock_logger,
            "New question",
            retrieved_context="Some context",
            retrieved_chunks_count=1,
            conversation_context_count=2
        )

        calls = [str(call) for call in mock_logger.debug.call_args_list]
        assert len(calls) >= 3  # Header + user query + at least contexts


class TestDebugLogLlmResponse:
    """Test debug_log_llm_response function."""

    def test_logs_nothing_when_level_above_debug(self, mock_logger):
        """Should not log when logger level is above DEBUG."""
        mock_logger.level = logging.INFO

        debug_log_llm_response(mock_logger, 250)

        mock_logger.debug.assert_not_called()

    def test_logs_when_level_is_debug(self, mock_logger):
        """Should log when logger level is DEBUG."""
        mock_logger.level = logging.DEBUG

        debug_log_llm_response(mock_logger, 350)

        assert mock_logger.debug.called
        calls = [str(call) for call in mock_logger.debug.call_args_list]
        assert any("LLM RESPONSE" in call for call in calls)

    def test_logs_response_length(self, mock_logger):
        """Should log the response length."""
        mock_logger.level = logging.DEBUG

        response_length = 1500
        debug_log_llm_response(mock_logger, response_length)

        calls = [str(call) for call in mock_logger.debug.call_args_list]
        assert any("1500" in call for call in calls)

    def test_logs_different_response_lengths(self, mock_logger):
        """Should correctly log various response lengths."""
        mock_logger.level = logging.DEBUG

        for length in [100, 500, 1000, 4000]:
            mock_logger.reset_mock()
            debug_log_llm_response(mock_logger, length)
            calls = [str(call) for call in mock_logger.debug.call_args_list]
            assert any(str(length) in call for call in calls)


class TestLoggingUtilityIntegration:
    """Integration tests for logging utilities."""

    def test_all_functions_respect_logger_level(self):
        """All logging functions should respect logger level."""
        logger = logging.getLogger("test_logger")

        # Set to WARNING level (above DEBUG)
        logger.setLevel(logging.WARNING)

        chunk = Mock()
        chunk.score = 0.95
        chunk.metadata = {}
        chunk.text = "Test"

        # These should not raise any exceptions even though they check logger.level
        debug_log_rag_retrieval(logger, [chunk])
        debug_log_llm_context(logger, "test")
        debug_log_llm_response(logger, 100)

    def test_logging_with_real_logger(self, caplog):
        """Test with real logger to verify messages are logged."""
        logger = logging.getLogger("test_real")
        logger.setLevel(logging.DEBUG)

        with caplog.at_level(logging.DEBUG, logger="test_real"):
            debug_log_rag_retrieval(logger, [])
            debug_log_llm_context(logger, "query")
            debug_log_llm_response(logger, 200)

        # Check that messages were logged
        assert any("RAG RETRIEVAL" in record.message for record in caplog.records)
        assert any("SENDING TO LLM" in record.message for record in caplog.records)
        assert any("LLM RESPONSE" in record.message for record in caplog.records)

    def test_emoji_present_in_logs(self, caplog):
        """Verify emoji decorations are in the logged messages."""
        logger = logging.getLogger("test_emoji")
        logger.setLevel(logging.DEBUG)

        with caplog.at_level(logging.DEBUG, logger="test_emoji"):
            debug_log_rag_retrieval(logger, [])
            debug_log_llm_context(logger, "test")
            debug_log_llm_response(logger, 100)

        # Check for emojis (📚, 📤, 📥)
        all_messages = " ".join(record.message for record in caplog.records)
        assert "📚" in all_messages  # RAG emoji
        assert "📤" in all_messages  # Sending emoji
        assert "📥" in all_messages  # Response emoji
