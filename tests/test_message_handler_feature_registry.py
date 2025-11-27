"""Tests for MessageHandler integration with FeatureRegistry."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from telegram import Update, User, Message, Chat
from telegram.ext import ContextTypes
from src.handlers.message_handler import MessageHandler
from src.core.features import FeatureRegistry, FeatureStatus
from src.config import Config
from src.core.llm import LLMClient
from src.core.db import ConversationDatabase
from src.services.retrieval_service import RetrievalService
from src.services.embedding_service import EmbeddingService


class TestMessageHandlerFeatureRegistry:
    """Test MessageHandler integration with FeatureRegistry."""

    @pytest.fixture
    def feature_registry(self):
        """Create a feature registry for testing."""
        return FeatureRegistry()

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = MagicMock(spec=Config)
        config.enable_document_selection = True
        return config

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        return MagicMock(spec=LLMClient)

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        return MagicMock(spec=ConversationDatabase)

    @pytest.fixture
    def mock_retrieval_service(self):
        """Create a mock retrieval service."""
        service = MagicMock(spec=RetrievalService)
        service.should_use_retrieval.return_value = True
        return service

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        return MagicMock(spec=EmbeddingService)

    def test_message_handler_accepts_feature_registry(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        feature_registry,
    ):
        """Test that MessageHandler accepts optional feature registry."""
        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            feature_registry=feature_registry,
        )

        assert handler.feature_registry is feature_registry

    def test_message_handler_creates_default_registry_if_not_provided(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
    ):
        """Test that MessageHandler creates default registry if not provided."""
        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
        )

        assert handler.feature_registry is not None
        assert isinstance(handler.feature_registry, FeatureRegistry)

    def test_retrieve_documents_checks_feature_availability(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        feature_registry,
    ):
        """Test that _retrieve_documents checks feature registry."""
        feature_registry.register_feature("rag_retrieval", FeatureStatus.UNAVAILABLE)

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry,
        )

        # Retrieve documents should return empty list
        result = handler._retrieve_documents("test query")
        assert result == []
        # Retrieval service should not be called
        mock_retrieval_service.retrieve_context.assert_not_called()

    def test_retrieve_documents_uses_service_when_feature_enabled(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        feature_registry,
    ):
        """Test that _retrieve_documents uses service when feature is enabled."""
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)
        mock_retrieval_service.should_use_retrieval.return_value = True
        mock_retrieval_service.retrieve_context.return_value = []

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry,
        )

        result = handler._retrieve_documents("test query")
        # Service should be called
        mock_retrieval_service.retrieve_context.assert_called_once()

    def test_retrieve_documents_logs_unavailable_reason(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        feature_registry,
    ):
        """Test that _retrieve_documents logs the reason for unavailability."""
        feature_registry.register_feature(
            "rag_retrieval",
            FeatureStatus.UNAVAILABLE,
            reason="Qdrant server not responding",
        )

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry,
        )

        with patch("src.handlers.message_handler.logger") as mock_logger:
            handler._retrieve_documents("test query")
            # Should log the reason
            mock_logger.debug.assert_called()
            debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
            assert any("Qdrant server not responding" in call for call in debug_calls)

    def test_retrieve_documents_without_feature_registration(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        feature_registry,
    ):
        """Test that _retrieve_documents handles unregistered features gracefully."""
        # Don't register any feature
        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry,
        )

        with patch("src.handlers.message_handler.logger") as mock_logger:
            result = handler._retrieve_documents("test query")
            # Should return empty list
            assert result == []
            # Should log debug message about unregistered feature
            mock_logger.debug.assert_called()

    def test_document_lookup_tool_initialized_when_features_available(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        mock_embedding_service,
        feature_registry,
    ):
        """Test that document lookup tool is initialized when features are available."""
        with patch(
            "src.handlers.message_handler.DocumentLookupTool"
        ) as mock_tool_class:
            mock_tool = MagicMock()
            mock_tool_class.return_value = mock_tool

            handler = MessageHandler(
                mock_llm_client,
                mock_db,
                mock_config,
                retrieval_service=mock_retrieval_service,
                embedding_service=mock_embedding_service,
                feature_registry=feature_registry,
            )

            # Document lookup tool should be initialized
            assert handler.document_lookup_tool is not None

    def test_document_lookup_tool_not_initialized_when_disabled_by_config(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        mock_embedding_service,
        feature_registry,
    ):
        """Test that document lookup tool is not initialized when disabled."""
        mock_config.enable_document_selection = False

        with patch(
            "src.handlers.message_handler.DocumentLookupTool"
        ) as mock_tool_class:
            handler = MessageHandler(
                mock_llm_client,
                mock_db,
                mock_config,
                retrieval_service=mock_retrieval_service,
                embedding_service=mock_embedding_service,
                feature_registry=feature_registry,
            )

            # Document lookup tool should not be initialized
            assert handler.document_lookup_tool is None
            # Tool class should not be called
            mock_tool_class.assert_not_called()

    def test_feature_registry_used_for_explicit_feature_checks(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        feature_registry,
    ):
        """Test that feature registry is used for explicit feature availability checks."""
        # Set up feature registry with disabled RAG
        feature_registry.register_feature("rag_retrieval", FeatureStatus.DISABLED)

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=None,
            feature_registry=feature_registry,
        )

        # Feature should be available to check
        assert not handler.feature_registry.is_available("rag_retrieval")
        assert handler.feature_registry.get_feature_state("rag_retrieval") is not None

    def test_multiple_features_tracked_independently(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        mock_embedding_service,
        feature_registry,
    ):
        """Test that multiple features can be tracked independently."""
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)
        feature_registry.register_feature("document_selection", FeatureStatus.DISABLED)

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=mock_retrieval_service,
            embedding_service=mock_embedding_service,
            feature_registry=feature_registry,
        )

        # Both features should be tracked
        assert handler.feature_registry.is_available("rag_retrieval")
        assert not handler.feature_registry.is_available("document_selection")

    def test_feature_state_metadata_accessible(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        feature_registry,
    ):
        """Test that feature state metadata is accessible via registry."""
        metadata = {"error_code": "QDRANT_TIMEOUT", "retry_count": 3}
        feature_registry.register_feature(
            "rag_retrieval",
            FeatureStatus.UNAVAILABLE,
            reason="Connection timeout",
            metadata=metadata,
        )

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            feature_registry=feature_registry,
        )

        state = handler.feature_registry.get_feature_state("rag_retrieval")
        assert state.metadata == metadata

    def test_retrieve_documents_with_degraded_feature_status(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        feature_registry,
    ):
        """Test that _retrieve_documents handles degraded feature status."""
        feature_registry.register_feature(
            "rag_retrieval",
            FeatureStatus.DEGRADED,
            reason="Slow response times",
        )

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry,
        )

        # Degraded features are not available, so should return empty
        result = handler._retrieve_documents("test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_feature_registry_available_during_message_handling(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        mock_retrieval_service,
        feature_registry,
    ):
        """Test that feature registry is available during message handling."""
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)
        mock_retrieval_service.should_use_retrieval.return_value = True
        mock_retrieval_service.retrieve_context.return_value = []

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            retrieval_service=mock_retrieval_service,
            feature_registry=feature_registry,
        )

        # Verify feature registry is accessible
        assert handler.feature_registry is not None
        assert handler.feature_registry.is_available("rag_retrieval")

    def test_feature_registry_passed_from_bot_factory(
        self,
        mock_llm_client,
        mock_db,
        mock_config,
        feature_registry,
    ):
        """Test that feature registry from bot_factory is used in MessageHandler."""
        # Simulate bot_factory creating and passing registry
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)
        feature_registry.register_feature("document_selection", FeatureStatus.ENABLED)

        handler = MessageHandler(
            mock_llm_client,
            mock_db,
            mock_config,
            feature_registry=feature_registry,
        )

        # Both features from bot_factory should be accessible
        all_states = handler.feature_registry.get_all_states()
        assert "rag_retrieval" in all_states
        assert "document_selection" in all_states
