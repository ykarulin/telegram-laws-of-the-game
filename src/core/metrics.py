"""Metrics tracking for bot operations and feature health.

Tracks:
- Retrieval degradation events (errors, health check failures)
- Error types and frequencies
- Recovery events
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DegradationMetrics:
    """Metrics for a degradation event."""

    feature_name: str
    error_type: str  # e.g., "health_check", "embedding", "search", "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "feature": self.feature_name,
            "error_type": self.error_type,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "details": self.details,
        }


class MetricsCollector:
    """Collect and track metrics for bot operations."""

    def __init__(self):
        """Initialize metrics collector."""
        self._degradation_events: Dict[str, list[DegradationMetrics]] = {}
        self._recovery_count: Dict[str, int] = {}

    def record_degradation(
        self,
        feature_name: str,
        error_type: str,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a degradation event.

        Args:
            feature_name: Name of the feature that degraded
            error_type: Type of error (health_check, embedding, search, etc.)
            reason: Optional description of the failure
            details: Optional additional details
        """
        event = DegradationMetrics(
            feature_name=feature_name,
            error_type=error_type,
            reason=reason,
            details=details or {},
        )

        if feature_name not in self._degradation_events:
            self._degradation_events[feature_name] = []

        self._degradation_events[feature_name].append(event)
        logger.debug(f"Recorded degradation event: {event.to_dict()}")

    def record_recovery(self, feature_name: str) -> None:
        """Record a feature recovery event.

        Args:
            feature_name: Name of the feature that recovered
        """
        if feature_name not in self._recovery_count:
            self._recovery_count[feature_name] = 0

        self._recovery_count[feature_name] += 1
        logger.debug(f"Recorded recovery for {feature_name}")

    def get_degradation_count(self, feature_name: str) -> int:
        """Get total degradation events for a feature.

        Args:
            feature_name: Name of the feature

        Returns:
            Total count of degradation events
        """
        return len(self._degradation_events.get(feature_name, []))

    def get_recovery_count(self, feature_name: str) -> int:
        """Get total recovery events for a feature.

        Args:
            feature_name: Name of the feature

        Returns:
            Total count of recovery events
        """
        return self._recovery_count.get(feature_name, 0)

    def get_error_type_distribution(self, feature_name: str) -> Dict[str, int]:
        """Get distribution of error types for a feature.

        Args:
            feature_name: Name of the feature

        Returns:
            Dictionary mapping error_type to count
        """
        events = self._degradation_events.get(feature_name, [])
        distribution: Dict[str, int] = {}

        for event in events:
            if event.error_type not in distribution:
                distribution[event.error_type] = 0
            distribution[event.error_type] += 1

        return distribution

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all collected metrics.

        Returns:
            Dictionary with comprehensive metrics summary
        """
        summary: Dict[str, Any] = {}

        for feature_name in set(list(self._degradation_events.keys()) + list(self._recovery_count.keys())):
            summary[feature_name] = {
                "degradation_count": self.get_degradation_count(feature_name),
                "recovery_count": self.get_recovery_count(feature_name),
                "error_type_distribution": self.get_error_type_distribution(feature_name),
            }

        return summary

    def log_metrics_summary(self) -> None:
        """Log a summary of all collected metrics."""
        summary = self.get_metrics_summary()

        if not summary:
            logger.info("No degradation or recovery events recorded")
            return

        logger.info("=== Metrics Summary ===")
        for feature_name, metrics in summary.items():
            logger.info(f"Feature: {feature_name}")
            logger.info(f"  Degradation events: {metrics['degradation_count']}")
            logger.info(f"  Recovery events: {metrics['recovery_count']}")
            if metrics["error_type_distribution"]:
                error_dist = metrics["error_type_distribution"]
                dist_str = ", ".join(f"{k}={v}" for k, v in sorted(error_dist.items()))
                logger.info(f"  Error type distribution: {dist_str}")
