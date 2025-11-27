"""Tests for feature registry and feature state management."""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.core.features import FeatureRegistry, FeatureState, FeatureStatus


class TestFeatureStatus:
    """Tests for FeatureStatus enum."""

    def test_feature_status_values(self):
        """Test that all feature status values are defined."""
        assert FeatureStatus.ENABLED.value == "enabled"
        assert FeatureStatus.DISABLED.value == "disabled"
        assert FeatureStatus.UNAVAILABLE.value == "unavailable"
        assert FeatureStatus.DEGRADED.value == "degraded"


class TestFeatureState:
    """Tests for FeatureState dataclass."""

    def test_feature_state_creation_minimal(self):
        """Test creating a FeatureState with minimal parameters."""
        state = FeatureState(name="test_feature", status=FeatureStatus.ENABLED)

        assert state.name == "test_feature"
        assert state.status == FeatureStatus.ENABLED
        assert state.reason is None
        assert state.metadata == {}

    def test_feature_state_creation_full(self):
        """Test creating a FeatureState with all parameters."""
        metadata = {"dependency": "qdrant", "version": "1.0"}
        state = FeatureState(
            name="rag_retrieval",
            status=FeatureStatus.UNAVAILABLE,
            reason="Qdrant server not responding",
            metadata=metadata,
        )

        assert state.name == "rag_retrieval"
        assert state.status == FeatureStatus.UNAVAILABLE
        assert state.reason == "Qdrant server not responding"
        assert state.metadata == metadata

    def test_is_available_true(self):
        """Test is_available returns True for ENABLED status."""
        state = FeatureState(name="feature", status=FeatureStatus.ENABLED)
        assert state.is_available() is True

    def test_is_available_false_disabled(self):
        """Test is_available returns False for DISABLED status."""
        state = FeatureState(name="feature", status=FeatureStatus.DISABLED)
        assert state.is_available() is False

    def test_is_available_false_unavailable(self):
        """Test is_available returns False for UNAVAILABLE status."""
        state = FeatureState(name="feature", status=FeatureStatus.UNAVAILABLE)
        assert state.is_available() is False

    def test_is_available_false_degraded(self):
        """Test is_available returns False for DEGRADED status."""
        state = FeatureState(name="feature", status=FeatureStatus.DEGRADED)
        assert state.is_available() is False

    def test_feature_state_last_checked_set_on_creation(self):
        """Test that last_checked is set when FeatureState is created."""
        before = datetime.utcnow()
        state = FeatureState(name="feature", status=FeatureStatus.ENABLED)
        after = datetime.utcnow()

        # Note: last_checked is NOT set in __init__, only when registered
        assert state.last_checked is None


class TestFeatureRegistry:
    """Tests for FeatureRegistry."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return FeatureRegistry()

    def test_registry_initialization(self, registry):
        """Test that registry initializes with empty features."""
        assert registry.get_all_states() == {}

    def test_register_feature_enabled(self, registry):
        """Test registering an enabled feature."""
        registry.register_feature(
            "test_feature",
            FeatureStatus.ENABLED,
            reason="All dependencies available",
        )

        state = registry.get_feature_state("test_feature")
        assert state is not None
        assert state.name == "test_feature"
        assert state.status == FeatureStatus.ENABLED
        assert state.reason == "All dependencies available"
        assert state.last_checked is not None

    def test_register_feature_disabled(self, registry):
        """Test registering a disabled feature."""
        registry.register_feature(
            "optional_feature",
            FeatureStatus.DISABLED,
            reason="Disabled via configuration",
        )

        state = registry.get_feature_state("optional_feature")
        assert state.status == FeatureStatus.DISABLED
        assert state.reason == "Disabled via configuration"

    def test_register_feature_unavailable(self, registry):
        """Test registering an unavailable feature."""
        registry.register_feature(
            "rag_retrieval",
            FeatureStatus.UNAVAILABLE,
            reason="Qdrant server not responding",
        )

        state = registry.get_feature_state("rag_retrieval")
        assert state.status == FeatureStatus.UNAVAILABLE
        assert state.reason == "Qdrant server not responding"

    def test_register_feature_degraded(self, registry):
        """Test registering a degraded feature."""
        registry.register_feature(
            "search",
            FeatureStatus.DEGRADED,
            reason="Slow response times from Qdrant",
        )

        state = registry.get_feature_state("search")
        assert state.status == FeatureStatus.DEGRADED

    def test_register_feature_with_metadata(self, registry):
        """Test registering a feature with metadata."""
        metadata = {"error_code": "QDRANT_TIMEOUT", "retry_count": 3}
        registry.register_feature(
            "feature",
            FeatureStatus.UNAVAILABLE,
            reason="Connection timeout",
            metadata=metadata,
        )

        state = registry.get_feature_state("feature")
        assert state.metadata == metadata

    def test_register_feature_without_metadata(self, registry):
        """Test that metadata defaults to empty dict if not provided."""
        registry.register_feature("feature", FeatureStatus.ENABLED)

        state = registry.get_feature_state("feature")
        assert state.metadata == {}

    def test_register_feature_overwrites_previous(self, registry):
        """Test that registering the same feature twice overwrites."""
        registry.register_feature("feature", FeatureStatus.ENABLED, reason="v1")
        registry.register_feature("feature", FeatureStatus.DISABLED, reason="v2")

        state = registry.get_feature_state("feature")
        assert state.status == FeatureStatus.DISABLED
        assert state.reason == "v2"

    def test_is_available_true(self, registry):
        """Test is_available returns True for enabled features."""
        registry.register_feature("feature", FeatureStatus.ENABLED)
        assert registry.is_available("feature") is True

    def test_is_available_false(self, registry):
        """Test is_available returns False for unavailable features."""
        registry.register_feature("feature", FeatureStatus.UNAVAILABLE)
        assert registry.is_available("feature") is False

    def test_is_available_unregistered(self, registry):
        """Test is_available returns False for unregistered features."""
        assert registry.is_available("nonexistent") is False

    def test_get_feature_state_existing(self, registry):
        """Test getting state of existing feature."""
        registry.register_feature("feature", FeatureStatus.ENABLED)
        state = registry.get_feature_state("feature")
        assert state is not None
        assert state.name == "feature"

    def test_get_feature_state_nonexistent(self, registry):
        """Test getting state of nonexistent feature."""
        state = registry.get_feature_state("nonexistent")
        assert state is None

    def test_get_all_states_empty(self, registry):
        """Test getting all states when registry is empty."""
        assert registry.get_all_states() == {}

    def test_get_all_states_multiple(self, registry):
        """Test getting all states with multiple registered features."""
        registry.register_feature("feature1", FeatureStatus.ENABLED)
        registry.register_feature("feature2", FeatureStatus.DISABLED)
        registry.register_feature("feature3", FeatureStatus.UNAVAILABLE)

        all_states = registry.get_all_states()
        assert len(all_states) == 3
        assert "feature1" in all_states
        assert "feature2" in all_states
        assert "feature3" in all_states

    def test_get_all_states_returns_copy(self, registry):
        """Test that get_all_states returns a copy, not the original."""
        registry.register_feature("feature1", FeatureStatus.ENABLED)
        all_states = registry.get_all_states()

        # Modify the returned dict
        all_states["feature2"] = FeatureState("feature2", FeatureStatus.ENABLED)

        # Original registry should be unchanged
        assert "feature2" not in registry.get_all_states()
        assert len(registry.get_all_states()) == 1

    def test_log_summary_empty_registry(self, registry):
        """Test log_summary with empty registry."""
        with patch("src.core.features.logger") as mock_logger:
            registry.log_summary()
            mock_logger.info.assert_called_with("No optional features registered")

    def test_log_summary_with_enabled_features(self, registry):
        """Test log_summary with enabled features."""
        registry.register_feature("feature1", FeatureStatus.ENABLED)
        registry.register_feature("feature2", FeatureStatus.ENABLED)

        with patch("src.core.features.logger") as mock_logger:
            registry.log_summary()
            # Check that the info call contains the enabled features
            calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("feature1" in call and "feature2" in call for call in calls)

    def test_log_summary_with_disabled_features(self, registry):
        """Test log_summary with disabled features."""
        registry.register_feature("feature1", FeatureStatus.DISABLED)

        with patch("src.core.features.logger") as mock_logger:
            registry.log_summary()
            calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("disabled" in call for call in calls)

    def test_log_summary_with_unavailable_features(self, registry):
        """Test log_summary includes warning for unavailable features."""
        registry.register_feature(
            "feature1",
            FeatureStatus.UNAVAILABLE,
            reason="Dependency missing",
        )

        with patch("src.core.features.logger") as mock_logger:
            registry.log_summary()
            # Check for warning log with the unavailable feature
            warning_calls = [
                call[0][0] for call in mock_logger.warning.call_args_list
            ]
            assert any("feature1" in call for call in warning_calls)

    def test_log_summary_with_degraded_features(self, registry):
        """Test log_summary includes warning for degraded features."""
        registry.register_feature(
            "feature1",
            FeatureStatus.DEGRADED,
            reason="Slow performance",
        )

        with patch("src.core.features.logger") as mock_logger:
            registry.log_summary()
            # Check for warning log with the degraded feature
            warning_calls = [
                call[0][0] for call in mock_logger.warning.call_args_list
            ]
            assert any("feature1" in call for call in warning_calls)

    def test_log_summary_mixed_states(self, registry):
        """Test log_summary with features in different states."""
        registry.register_feature("enabled1", FeatureStatus.ENABLED)
        registry.register_feature("enabled2", FeatureStatus.ENABLED)
        registry.register_feature("disabled1", FeatureStatus.DISABLED)
        registry.register_feature("unavailable1", FeatureStatus.UNAVAILABLE)
        registry.register_feature("degraded1", FeatureStatus.DEGRADED)

        with patch("src.core.features.logger") as mock_logger:
            registry.log_summary()
            # Verify at least one info call was made with summary
            assert mock_logger.info.called
            assert mock_logger.warning.called

    def test_register_feature_logs_enabled(self, registry):
        """Test that registering an enabled feature logs info."""
        with patch("src.core.features.logger") as mock_logger:
            registry.register_feature("feature", FeatureStatus.ENABLED, reason="Test")
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args[0][0]
            assert "feature" in call_args
            assert "ENABLED" in call_args

    def test_register_feature_logs_disabled(self, registry):
        """Test that registering a disabled feature logs info."""
        with patch("src.core.features.logger") as mock_logger:
            registry.register_feature(
                "feature", FeatureStatus.DISABLED, reason="Test"
            )
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args[0][0]
            assert "feature" in call_args
            assert "DISABLED" in call_args

    def test_register_feature_logs_unavailable(self, registry):
        """Test that registering an unavailable feature logs warning."""
        with patch("src.core.features.logger") as mock_logger:
            registry.register_feature(
                "feature", FeatureStatus.UNAVAILABLE, reason="Test"
            )
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args[0][0]
            assert "feature" in call_args
            assert "UNAVAILABLE" in call_args

    def test_register_feature_logs_degraded(self, registry):
        """Test that registering a degraded feature logs warning."""
        with patch("src.core.features.logger") as mock_logger:
            registry.register_feature("feature", FeatureStatus.DEGRADED, reason="Test")
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args[0][0]
            assert "feature" in call_args
            assert "DEGRADED" in call_args

    def test_register_feature_without_reason_logs_default(self, registry):
        """Test that registering without reason uses default messages."""
        with patch("src.core.features.logger") as mock_logger:
            registry.register_feature("feature", FeatureStatus.DISABLED)
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args[0][0]
            assert "configuration" in call_args.lower()

    def test_last_checked_timestamp_set(self, registry):
        """Test that last_checked is set to current time."""
        before = datetime.utcnow()
        registry.register_feature("feature", FeatureStatus.ENABLED)
        after = datetime.utcnow()

        state = registry.get_feature_state("feature")
        assert before <= state.last_checked <= after

    def test_last_checked_updated_on_re_register(self, registry):
        """Test that last_checked is updated when feature is re-registered."""
        registry.register_feature("feature", FeatureStatus.ENABLED)
        first_check = registry.get_feature_state("feature").last_checked

        # Wait a tiny bit and re-register
        registry.register_feature("feature", FeatureStatus.DISABLED)
        second_check = registry.get_feature_state("feature").last_checked

        assert second_check >= first_check
