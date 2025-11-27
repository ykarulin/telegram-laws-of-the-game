"""Tests for runtime degradation detection and handling.

Tests the new runtime health checks, degradation tracking, and user-facing
fallback notices when retrieval systems fail after startup.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from src.core.features import FeatureRegistry, FeatureStatus
from src.core.metrics import MetricsCollector, DegradationMetrics
from src.services.retrieval_service import RetrievalService, get_metrics_collector
from src.exceptions import RetrievalError
from src.config import Config


class TestRetrievalError:
    """Tests for RetrievalError exception."""

    def test_retrieval_error_creation(self):
        """Test creating a RetrievalError with error type."""
        error = RetrievalError("Health check failed", error_type="health_check")
        assert str(error) == "Health check failed"
        assert error.error_type == "health_check"

    def test_retrieval_error_default_type(self):
        """Test RetrievalError defaults to unknown type."""
        error = RetrievalError("Some error")
        assert error.error_type == "unknown"

    def test_retrieval_error_types(self):
        """Test various error types."""
        types = ["health_check", "embedding", "search", "unknown"]
        for error_type in types:
            error = RetrievalError("Test", error_type=error_type)
            assert error.error_type == error_type


class TestDegradationMetrics:
    """Tests for DegradationMetrics dataclass."""

    def test_degradation_metrics_creation(self):
        """Test creating a DegradationMetrics object."""
        metrics = DegradationMetrics(
            feature_name="rag_retrieval",
            error_type="health_check",
            reason="Qdrant not responding",
        )
        assert metrics.feature_name == "rag_retrieval"
        assert metrics.error_type == "health_check"
        assert metrics.reason == "Qdrant not responding"

    def test_degradation_metrics_to_dict(self):
        """Test converting DegradationMetrics to dictionary."""
        metrics = DegradationMetrics(
            feature_name="rag_retrieval",
            error_type="embedding",
            reason="OpenAI API timeout",
            details={"retry_count": 3},
        )
        result = metrics.to_dict()

        assert result["feature"] == "rag_retrieval"
        assert result["error_type"] == "embedding"
        assert result["reason"] == "OpenAI API timeout"
        assert result["details"] == {"retry_count": 3}
        assert "timestamp" in result


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Create a fresh metrics collector for each test."""
        return MetricsCollector()

    def test_metrics_collector_initialization(self, collector):
        """Test that collector initializes with empty metrics."""
        assert collector.get_metrics_summary() == {}

    def test_record_degradation(self, collector):
        """Test recording a degradation event."""
        collector.record_degradation(
            "rag_retrieval",
            "health_check",
            reason="Health check failed",
        )

        count = collector.get_degradation_count("rag_retrieval")
        assert count == 1

    def test_record_multiple_degradations(self, collector):
        """Test recording multiple degradation events."""
        for i in range(5):
            collector.record_degradation(
                "rag_retrieval",
                "health_check" if i % 2 == 0 else "search",
            )

        count = collector.get_degradation_count("rag_retrieval")
        assert count == 5

    def test_get_degradation_count_nonexistent(self, collector):
        """Test getting degradation count for nonexistent feature."""
        count = collector.get_degradation_count("nonexistent")
        assert count == 0

    def test_record_recovery(self, collector):
        """Test recording recovery events."""
        collector.record_recovery("rag_retrieval")
        collector.record_recovery("rag_retrieval")

        count = collector.get_recovery_count("rag_retrieval")
        assert count == 2

    def test_get_error_type_distribution(self, collector):
        """Test getting distribution of error types."""
        collector.record_degradation("rag_retrieval", "health_check")
        collector.record_degradation("rag_retrieval", "health_check")
        collector.record_degradation("rag_retrieval", "embedding")
        collector.record_degradation("rag_retrieval", "search")

        distribution = collector.get_error_type_distribution("rag_retrieval")
        assert distribution["health_check"] == 2
        assert distribution["embedding"] == 1
        assert distribution["search"] == 1

    def test_get_metrics_summary(self, collector):
        """Test getting comprehensive metrics summary."""
        collector.record_degradation("feature1", "health_check")
        collector.record_recovery("feature1")
        collector.record_degradation("feature2", "embedding")

        summary = collector.get_metrics_summary()
        assert "feature1" in summary
        assert "feature2" in summary
        assert summary["feature1"]["degradation_count"] == 1
        assert summary["feature1"]["recovery_count"] == 1

    def test_log_metrics_summary_empty(self, collector):
        """Test logging metrics summary when empty."""
        with patch("src.core.metrics.logger") as mock_logger:
            collector.log_metrics_summary()
            mock_logger.info.assert_called_with("No degradation or recovery events recorded")

    def test_log_metrics_summary_with_data(self, collector):
        """Test logging metrics summary with data."""
        collector.record_degradation("rag_retrieval", "health_check")
        collector.record_degradation("rag_retrieval", "health_check")
        collector.record_degradation("rag_retrieval", "embedding")
        collector.record_recovery("rag_retrieval")

        with patch("src.core.metrics.logger") as mock_logger:
            collector.log_metrics_summary()
            # Should log summary header and feature details
            assert mock_logger.info.call_count >= 3


class TestFeatureRegistryDegradation:
    """Tests for FeatureRegistry degradation tracking."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return FeatureRegistry()

    def test_update_status_degradation(self, registry):
        """Test updating feature to degraded status."""
        registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)
        registry.update_status(
            "rag_retrieval",
            FeatureStatus.DEGRADED,
            reason="Runtime health check failed",
        )

        state = registry.get_feature_state("rag_retrieval")
        assert state.status == FeatureStatus.DEGRADED
        assert state.reason == "Runtime health check failed"

    def test_update_status_increments_degradation_count(self, registry):
        """Test that degradation count increments on transition to DEGRADED."""
        registry.register_feature("feature", FeatureStatus.ENABLED)

        # First degradation (transition from ENABLED to DEGRADED)
        registry.update_status("feature", FeatureStatus.DEGRADED, reason="Error 1")
        assert registry.get_feature_state("feature").degradation_count == 1

        # Recover to ENABLED
        registry.update_status("feature", FeatureStatus.ENABLED, reason="Recovered")
        assert registry.get_feature_state("feature").degradation_count == 1

        # Second degradation (transition from ENABLED to DEGRADED again)
        registry.update_status("feature", FeatureStatus.DEGRADED, reason="Error 2")
        assert registry.get_feature_state("feature").degradation_count == 2

    def test_get_degradation_count(self, registry):
        """Test getting degradation count across multiple degradations."""
        registry.register_feature("feature", FeatureStatus.ENABLED)

        # First degradation
        registry.update_status("feature", FeatureStatus.DEGRADED)
        assert registry.get_degradation_count("feature") == 1

        # Recover and degrade again
        registry.update_status("feature", FeatureStatus.ENABLED)
        registry.update_status("feature", FeatureStatus.DEGRADED)

        assert registry.get_degradation_count("feature") == 2

    def test_get_degradation_count_unregistered(self, registry):
        """Test getting degradation count for unregistered feature."""
        assert registry.get_degradation_count("nonexistent") == 0

    def test_is_degraded(self, registry):
        """Test is_degraded method on FeatureState."""
        registry.register_feature("feature", FeatureStatus.DEGRADED)
        state = registry.get_feature_state("feature")
        assert state.is_degraded() is True

    def test_is_degraded_false_when_enabled(self, registry):
        """Test is_degraded returns False for enabled features."""
        registry.register_feature("feature", FeatureStatus.ENABLED)
        state = registry.get_feature_state("feature")
        assert state.is_degraded() is False

    def test_update_status_logs_degradation_warning(self, registry):
        """Test that degradation is logged as warning."""
        registry.register_feature("feature", FeatureStatus.ENABLED)

        with patch("src.core.features.logger") as mock_logger:
            registry.update_status(
                "feature",
                FeatureStatus.DEGRADED,
                reason="Test degradation",
            )
            # Should log warning about degradation
            warning_calls = mock_logger.warning.call_args_list
            assert any("degraded" in str(call) for call in warning_calls)

    def test_update_status_logs_recovery_info(self, registry):
        """Test that recovery is logged as info."""
        registry.register_feature("feature", FeatureStatus.DEGRADED)

        with patch("src.core.features.logger") as mock_logger:
            registry.update_status(
                "feature",
                FeatureStatus.ENABLED,
                reason="Service recovered",
            )
            # Should log info about recovery
            # Check that info was called with a message containing "recovered"
            assert mock_logger.info.called
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("recovered" in call.lower() for call in info_calls)


class TestRetrievalServiceRuntimeDegradation:
    """Tests for runtime degradation in RetrievalService."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        config = MagicMock(spec=Config)
        config.qdrant_host = "localhost"
        config.qdrant_port = 6333
        config.qdrant_api_key = None
        config.qdrant_collection_name = "test_collection"
        config.top_k_retrievals = 3
        config.similarity_threshold = 0.7
        config.rag_dynamic_threshold_margin = None
        config.embedding_model = "text-embedding-3-small"
        return config

    @pytest.fixture
    def embedding_service(self):
        """Create a mock embedding service."""
        return MagicMock()

    @pytest.fixture
    def feature_registry(self):
        """Create a fresh feature registry."""
        return FeatureRegistry()

    @pytest.fixture
    def retrieval_service(self, config, embedding_service, feature_registry):
        """Create a retrieval service with mocked dependencies."""
        service = RetrievalService(
            config, embedding_service, db_session=None, feature_registry=feature_registry
        )
        # Mock the vector_db
        service.vector_db = MagicMock()
        return service

    def test_health_check_failure_marks_feature_degraded(
        self, retrieval_service, feature_registry
    ):
        """Test that health check failure marks feature as degraded."""
        retrieval_service.vector_db.health_check.return_value = False

        # Register feature as enabled first
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)

        # Call retrieve_context which should detect health check failure
        result = retrieval_service.retrieve_context("test query")

        assert result == []
        state = feature_registry.get_feature_state("rag_retrieval")
        assert state.is_degraded()

    def test_embedding_failure_marks_feature_degraded(
        self, retrieval_service, feature_registry, embedding_service
    ):
        """Test that embedding failure marks feature as degraded."""
        retrieval_service.vector_db.health_check.return_value = True
        embedding_service.embed_text.return_value = None

        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)

        result = retrieval_service.retrieve_context("test query")

        assert result == []
        state = feature_registry.get_feature_state("rag_retrieval")
        assert state.is_degraded()

    def test_retrieval_exception_marks_feature_degraded(
        self, retrieval_service, feature_registry
    ):
        """Test that retrieval exceptions mark feature as degraded."""
        retrieval_service.vector_db.health_check.return_value = True
        retrieval_service.vector_db.search.side_effect = Exception("Connection error")
        retrieval_service.embedding_service.embed_text.return_value = [0.1, 0.2]

        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)

        result = retrieval_service.retrieve_context("test query")

        assert result == []
        state = feature_registry.get_feature_state("rag_retrieval")
        assert state.is_degraded()

    def test_metrics_recorded_on_health_check_failure(
        self, retrieval_service, feature_registry
    ):
        """Test that metrics are recorded when health check fails."""
        retrieval_service.vector_db.health_check.return_value = False
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)

        # Get metrics collector before test
        collector = get_metrics_collector()
        initial_count = collector.get_degradation_count("rag_retrieval")

        retrieval_service.retrieve_context("test query")

        # Should have recorded one more degradation
        final_count = collector.get_degradation_count("rag_retrieval")
        assert final_count > initial_count

    def test_metrics_recorded_on_embedding_failure(
        self, retrieval_service, feature_registry
    ):
        """Test that metrics are recorded when embedding fails."""
        retrieval_service.vector_db.health_check.return_value = True
        retrieval_service.embedding_service.embed_text.return_value = None
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)

        collector = get_metrics_collector()
        initial_count = collector.get_degradation_count("rag_retrieval")

        retrieval_service.retrieve_context("test query")

        final_count = collector.get_degradation_count("rag_retrieval")
        assert final_count > initial_count

    def test_retrieve_and_format_includes_degradation_notice(
        self, retrieval_service, feature_registry
    ):
        """Test that retrieve_and_format includes fallback notice when degraded."""
        retrieval_service.vector_db.health_check.return_value = False
        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)

        result = retrieval_service.retrieve_and_format("test query")

        # Should include the degradation notice
        assert "unavailable" in result
        assert "temporary service issue" in result

    def test_successful_retrieval_does_not_include_notice(
        self, retrieval_service, feature_registry
    ):
        """Test that successful retrieval does not include degradation notice."""
        retrieval_service.vector_db.health_check.return_value = True
        retrieval_service.embedding_service.embed_text.return_value = [0.1, 0.2]

        # Mock successful search result
        from src.core.vector_db import RetrievedChunk
        chunk = RetrievedChunk(
            chunk_id="chunk_1",
            text="Test content",
            score=0.8,
            metadata={"document_name": "Test Doc", "section": "1"},
        )
        retrieval_service.vector_db.search.return_value = [chunk]

        feature_registry.register_feature("rag_retrieval", FeatureStatus.ENABLED)

        result = retrieval_service.retrieve_and_format("test query")

        # Should NOT include degradation notice
        assert "unavailable" not in result
        assert "temporary service issue" not in result
        assert "Test content" in result
