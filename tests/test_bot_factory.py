"""Tests for bot factory and application creation."""
import pytest
from unittest.mock import MagicMock, patch
from telegram.ext import Application
from src.bot_factory import create_application
from src.config import Config, Environment
from src.core.features import FeatureStatus


class TestBotFactory:
    """Test bot factory creation and configuration."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing."""
        config = MagicMock(spec=Config)
        config.environment = Environment.TESTING
        config.telegram_bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        config.openai_api_key = "sk-test-key"
        config.openai_model = "gpt-4-turbo"
        config.openai_max_tokens = 4096
        config.openai_temperature = 0.7
        config.database_url = "postgresql://test:test@localhost/test"
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "football_documents"
        config.embedding_model = "text-embedding-3-small"
        config.top_k_retrievals = 5
        config.similarity_threshold = 0.55
        return config

    def test_create_application_success(self, mock_config):
        """Test successful application creation."""
        with patch("src.bot_factory.LLMClient") as mock_llm_class:
            with patch("src.bot_factory.ConversationDatabase") as mock_db_class:
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        mock_llm_class.return_value = MagicMock()
                        mock_db_class.return_value = MagicMock()
                        mock_embed_class.return_value = MagicMock()
                        mock_retrieval_class.return_value = MagicMock()

                        app = create_application(mock_config)

                        assert isinstance(app, Application)
                        assert app is not None

    def test_create_application_initializes_llm_client(self, mock_config):
        """Test that LLM client is properly initialized."""
        with patch("src.bot_factory.LLMClient") as mock_llm_class:
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        mock_llm_instance = MagicMock()
                        mock_llm_class.return_value = mock_llm_instance

                        create_application(mock_config)

                        mock_llm_class.assert_called_once_with(
                            api_key=mock_config.openai_api_key,
                            model=mock_config.openai_model,
                            max_tokens=mock_config.openai_max_tokens,
                            temperature=mock_config.openai_temperature,
                        )

    def test_create_application_initializes_database(self, mock_config):
        """Test that database is properly initialized."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase") as mock_db_class:
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        mock_db_instance = MagicMock()
                        mock_db_class.return_value = mock_db_instance

                        create_application(mock_config)

                        mock_db_class.assert_called_once_with(mock_config.database_url)

    def test_create_application_initializes_embedding_service(self, mock_config):
        """Test that embedding service is properly initialized."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService"):
                        mock_embed_instance = MagicMock()
                        mock_embed_class.return_value = mock_embed_instance

                        create_application(mock_config)

                        mock_embed_class.assert_called_once_with(
                            api_key=mock_config.openai_api_key,
                            model=mock_config.embedding_model
                        )

    def test_create_application_initializes_retrieval_service(self, mock_config):
        """Test that retrieval service is properly initialized."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        mock_embed_instance = MagicMock()
                        mock_embed_class.return_value = mock_embed_instance
                        mock_retrieval_instance = MagicMock()
                        mock_retrieval_class.return_value = mock_retrieval_instance

                        create_application(mock_config)

                        mock_retrieval_class.assert_called_once_with(
                            mock_config,
                            mock_embed_instance
                        )

    def test_create_application_handles_embedding_service_error(self, mock_config):
        """Test graceful handling when embedding service fails."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        # Make embedding service raise an error
                        mock_embed_class.side_effect = Exception("Embedding service error")

                        app = create_application(mock_config)

                        # Application should still be created
                        assert isinstance(app, Application)
                        # Retrieval service should not be called
                        mock_retrieval_class.assert_not_called()

    def test_create_application_passes_config_to_message_handler(self, mock_config):
        """Test that message handler receives correct configuration."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config)

                            # Verify message handler was created with correct params
                            assert mock_handler_class.called
                            call_args = mock_handler_class.call_args
                            # Last argument should be the config
                            assert call_args[0][2] == mock_config

    def test_create_application_registers_text_message_handler(self, mock_config):
        """Test that text message handler is registered."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        app = create_application(mock_config)

                        # Verify a handler was added
                        assert len(app.handlers) > 0

    def test_create_application_with_different_environments(self):
        """Test application creation with different environments."""
        for env in [Environment.DEVELOPMENT, Environment.TESTING, Environment.PRODUCTION]:
            config = MagicMock(spec=Config)
            config.environment = env
            config.telegram_bot_token = "test-token"
            config.openai_api_key = "test-key"
            config.openai_model = "gpt-4"
            config.openai_max_tokens = 4096
            config.openai_temperature = 0.7
            config.database_url = "postgresql://test"
            config.qdrant_host = "localhost"
            config.qdrant_port = 6333
            config.qdrant_api_key = None
            config.embedding_model = "text-embedding-3-small"

            with patch("src.bot_factory.LLMClient"):
                with patch("src.bot_factory.ConversationDatabase"):
                    with patch("src.bot_factory.EmbeddingService"):
                        with patch("src.bot_factory.RetrievalService"):
                            app = create_application(config)
                            assert isinstance(app, Application)

    def test_create_application_with_api_key_for_qdrant(self, mock_config):
        """Test application creation with Qdrant API key."""
        mock_config.qdrant_api_key = "test-api-key"

        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        app = create_application(mock_config)
                        assert isinstance(app, Application)

    def test_create_application_logs_success(self, mock_config):
        """Test that success message is logged."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        with patch("src.bot_factory.logger") as mock_logger:
                            create_application(mock_config)

                            # Check that success messages were logged
                            assert mock_logger.info.called

    def test_create_application_retrieval_service_disabled_gracefully(self, mock_config):
        """Test that application works when retrieval service fails."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            # Embedding service works but retrieval service fails
                            mock_embed_class.return_value = MagicMock()
                            mock_retrieval_class.side_effect = Exception("Retrieval error")
                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            app = create_application(mock_config)

                            # App should still be created
                            assert isinstance(app, Application)
                            # Message handler should be called with None for retrieval_service
                            call_args = mock_handler_class.call_args
                            # Fourth argument (retrieval_service) should be None
                            assert call_args[0][3] is None

    def test_create_application_token_validation(self, mock_config):
        """Test that bot token is properly set."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        app = create_application(mock_config)

                        # Verify app was created with token
                        assert app is not None
                        assert isinstance(app, Application)

    def test_create_application_multiple_calls_independent(self, mock_config):
        """Test that multiple application instances are independent."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        app1 = create_application(mock_config)
                        app2 = create_application(mock_config)

                        # Should be different instances
                        assert app1 is not app2
                        assert isinstance(app1, Application)
                        assert isinstance(app2, Application)

    def test_create_application_with_custom_temperature(self, mock_config):
        """Test application with custom LLM temperature."""
        mock_config.openai_temperature = 0.2

        with patch("src.bot_factory.LLMClient") as mock_llm_class:
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        create_application(mock_config)

                        # Verify temperature was passed correctly
                        call_args = mock_llm_class.call_args
                        assert call_args.kwargs["temperature"] == 0.2


class TestBotFactoryFeatureRegistry:
    """Test FeatureRegistry integration in bot factory."""

    @pytest.fixture
    def mock_config_with_features(self):
        """Create a mock config for feature registry testing."""
        config = MagicMock(spec=Config)
        config.environment = Environment.TESTING
        config.telegram_bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        config.openai_api_key = "sk-test-key"
        config.openai_model = "gpt-4-turbo"
        config.openai_max_tokens = 4096
        config.openai_temperature = 0.7
        config.database_url = "postgresql://test:test@localhost/test"
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "football_documents"
        config.embedding_model = "text-embedding-3-small"
        config.top_k_retrievals = 5
        config.similarity_threshold = 0.55
        config.enable_document_selection = True
        return config

    def test_feature_registry_created(self, mock_config_with_features):
        """Test that feature registry is created during application creation."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config_with_features)

                            # Message handler should receive feature registry
                            call_args = mock_handler_class.call_args
                            assert len(call_args[0]) >= 6
                            feature_registry = call_args[0][5]
                            assert feature_registry is not None

    def test_rag_retrieval_feature_enabled_when_healthy(self, mock_config_with_features):
        """Test that rag_retrieval feature is marked as ENABLED when Qdrant is healthy."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            mock_embed_instance = MagicMock()
                            mock_embed_class.return_value = mock_embed_instance

                            mock_retrieval_instance = MagicMock()
                            mock_retrieval_instance.should_use_retrieval.return_value = True
                            mock_retrieval_class.return_value = mock_retrieval_instance

                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config_with_features)

                            # Get feature registry from message handler call
                            feature_registry = mock_handler_class.call_args[0][5]
                            rag_state = feature_registry.get_feature_state("rag_retrieval")

                            assert rag_state is not None
                            assert rag_state.status == FeatureStatus.ENABLED

    def test_rag_retrieval_feature_unavailable_on_health_check_failure(
        self, mock_config_with_features
    ):
        """Test that rag_retrieval is UNAVAILABLE when health check fails."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            mock_embed_instance = MagicMock()
                            mock_embed_class.return_value = mock_embed_instance

                            # Health check returns False
                            mock_retrieval_instance = MagicMock()
                            mock_retrieval_instance.should_use_retrieval.return_value = False
                            mock_retrieval_class.return_value = mock_retrieval_instance

                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config_with_features)

                            # Get feature registry
                            feature_registry = mock_handler_class.call_args[0][5]
                            rag_state = feature_registry.get_feature_state("rag_retrieval")

                            assert rag_state is not None
                            assert rag_state.status == FeatureStatus.UNAVAILABLE

    def test_rag_retrieval_feature_unavailable_on_exception(
        self, mock_config_with_features
    ):
        """Test that rag_retrieval is UNAVAILABLE when initialization raises exception."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            # Embedding service works
                            mock_embed_class.return_value = MagicMock()

                            # Retrieval service fails
                            mock_retrieval_class.side_effect = Exception("Qdrant connection failed")

                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config_with_features)

                            # Get feature registry
                            feature_registry = mock_handler_class.call_args[0][5]
                            rag_state = feature_registry.get_feature_state("rag_retrieval")

                            assert rag_state is not None
                            assert rag_state.status == FeatureStatus.UNAVAILABLE
                            assert "Initialization failed" in rag_state.reason

    def test_document_selection_feature_enabled(self, mock_config_with_features):
        """Test that document_selection feature is ENABLED when all conditions met."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService") as mock_embed_class:
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            mock_embed_class.return_value = MagicMock()
                            mock_retrieval_instance = MagicMock()
                            mock_retrieval_instance.should_use_retrieval.return_value = True
                            mock_retrieval_class.return_value = mock_retrieval_instance

                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config_with_features)

                            feature_registry = mock_handler_class.call_args[0][5]
                            doc_sel_state = feature_registry.get_feature_state(
                                "document_selection"
                            )

                            assert doc_sel_state is not None
                            assert doc_sel_state.status == FeatureStatus.ENABLED

    def test_document_selection_feature_disabled_by_config(self, mock_config_with_features):
        """Test that document_selection feature is DISABLED when config disables it."""
        mock_config_with_features.enable_document_selection = False

        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config_with_features)

                            feature_registry = mock_handler_class.call_args[0][5]
                            doc_sel_state = feature_registry.get_feature_state(
                                "document_selection"
                            )

                            assert doc_sel_state is not None
                            assert doc_sel_state.status == FeatureStatus.DISABLED

    def test_document_selection_feature_unavailable_without_retrieval(
        self, mock_config_with_features
    ):
        """Test that document_selection is UNAVAILABLE without retrieval service."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService") as mock_retrieval_class:
                        with patch("src.bot_factory.MessageHandler") as mock_handler_class:
                            # Retrieval service fails
                            mock_retrieval_class.side_effect = Exception("Failed")

                            mock_handler = MagicMock()
                            mock_handler_class.return_value = mock_handler

                            create_application(mock_config_with_features)

                            feature_registry = mock_handler_class.call_args[0][5]
                            doc_sel_state = feature_registry.get_feature_state(
                                "document_selection"
                            )

                            assert doc_sel_state is not None
                            assert doc_sel_state.status == FeatureStatus.UNAVAILABLE

    def test_feature_registry_summary_logged(self, mock_config_with_features):
        """Test that feature registry summary is logged on creation."""
        with patch("src.bot_factory.LLMClient"):
            with patch("src.bot_factory.ConversationDatabase"):
                with patch("src.bot_factory.EmbeddingService"):
                    with patch("src.bot_factory.RetrievalService"):
                        with patch("src.bot_factory.logger") as mock_logger:
                            create_application(mock_config_with_features)

                            # Verify summary logging was called
                            info_calls = [
                                call[0][0] for call in mock_logger.info.call_args_list
                            ]
                            # Should log feature availability summary
                            assert any("Feature availability" in call for call in info_calls)
