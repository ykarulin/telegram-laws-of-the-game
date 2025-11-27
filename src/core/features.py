"""Feature availability registry for optional bot capabilities."""

import logging
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class FeatureStatus(Enum):
    """Status of an optional feature."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


@dataclass
class FeatureState:
    """State information for a feature."""

    name: str
    status: FeatureStatus
    reason: Optional[str] = None
    last_checked: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def is_available(self) -> bool:
        """Check if feature is usable."""
        return self.status == FeatureStatus.ENABLED


class FeatureRegistry:
    """Central registry for tracking optional feature availability."""

    def __init__(self):
        """Initialize the feature registry."""
        self._features: Dict[str, FeatureState] = {}

    def register_feature(
        self,
        name: str,
        status: FeatureStatus,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register or update a feature's state.

        Args:
            name: Feature name
            status: Current status of the feature
            reason: Optional reason for the status
            metadata: Optional additional metadata
        """
        self._features[name] = FeatureState(
            name=name,
            status=status,
            reason=reason,
            last_checked=datetime.utcnow(),
            metadata=metadata or {},
        )

        # Log feature state changes
        if status == FeatureStatus.ENABLED:
            reason_str = f": {reason}" if reason else ""
            logger.info(f"Feature '{name}' is ENABLED{reason_str}")
        elif status == FeatureStatus.UNAVAILABLE:
            reason_str = reason or "unknown reason"
            logger.warning(f"Feature '{name}' is UNAVAILABLE: {reason_str}")
        elif status == FeatureStatus.DISABLED:
            reason_str = reason or "configuration"
            logger.info(f"Feature '{name}' is DISABLED: {reason_str}")
        elif status == FeatureStatus.DEGRADED:
            reason_str = reason or "unknown"
            logger.warning(f"Feature '{name}' is DEGRADED: {reason_str}")

    def get_feature_state(self, name: str) -> Optional[FeatureState]:
        """Get current state of a feature.

        Args:
            name: Feature name

        Returns:
            FeatureState if registered, None otherwise
        """
        return self._features.get(name)

    def is_available(self, name: str) -> bool:
        """Check if a feature is available for use.

        Args:
            name: Feature name

        Returns:
            True if feature is ENABLED, False otherwise
        """
        state = self._features.get(name)
        return state.is_available() if state else False

    def get_all_states(self) -> Dict[str, FeatureState]:
        """Get all registered feature states.

        Returns:
            Copy of all registered features
        """
        return self._features.copy()

    def log_summary(self) -> None:
        """Log a summary of all feature states."""
        if not self._features:
            logger.info("No optional features registered")
            return

        enabled = [
            name
            for name, state in self._features.items()
            if state.status == FeatureStatus.ENABLED
        ]
        unavailable = [
            name
            for name, state in self._features.items()
            if state.status == FeatureStatus.UNAVAILABLE
        ]
        disabled = [
            name
            for name, state in self._features.items()
            if state.status == FeatureStatus.DISABLED
        ]
        degraded = [
            name
            for name, state in self._features.items()
            if state.status == FeatureStatus.DEGRADED
        ]

        status_parts = []
        if enabled:
            status_parts.append(f"enabled={len(enabled)} ({', '.join(enabled)})")
        if disabled:
            status_parts.append(f"disabled={len(disabled)} ({', '.join(disabled)})")
        if unavailable:
            status_parts.append(f"unavailable={len(unavailable)} ({', '.join(unavailable)})")
        if degraded:
            status_parts.append(f"degraded={len(degraded)} ({', '.join(degraded)})")

        logger.info(f"Feature availability: {', '.join(status_parts) if status_parts else 'no features'}")

        # Log details for unavailable and degraded features
        for name in unavailable:
            state = self._features[name]
            logger.warning(f"  UNAVAILABLE - {name}: {state.reason}")
        for name in degraded:
            state = self._features[name]
            logger.warning(f"  DEGRADED - {name}: {state.reason}")
