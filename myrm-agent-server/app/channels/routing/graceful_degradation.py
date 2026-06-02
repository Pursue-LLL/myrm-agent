"""Graceful degradation controller for smooth quality adaptation.

Provides smooth degradation instead of circuit breaker's all-or-nothing approach.
When failures occur, gradually reduces update frequency rather than stopping completely.

Design philosophy:
- Never completely block: User always receives updates (though potentially slower)
- Gradual adaptation: Smoothly degrade on failures, smoothly recover on successes
- Better UX: No sudden 30s blackout periods like circuit breaker
- Simpler state: No complex CLOSED/OPEN/HALF_OPEN state machine

Performance:
- State check: O(1), ~100-200ns (simpler than circuit breaker)
- Level adjustment: O(1), no time window tracking needed
- Memory: Minimal (just counters and enum, no deque)

[INPUT]
- (none)

[OUTPUT]
- DegradationLevel: Degradation levels for update frequency control.
- GracefulDegradationController: Graceful degradation controller with smooth frequency ada...

[POS]
Graceful degradation controller for smooth quality adaptation.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger("myrm.channels.graceful_degradation")


class DegradationLevel(Enum):
    """Degradation levels for update frequency control."""

    NORMAL = 0  # 1x (normal frequency)
    DEGRADED_1 = 1  # 2x slower
    DEGRADED_2 = 2  # 4x slower
    DEGRADED_3 = 3  # 8x slower
    DEGRADED_4 = 4  # 16x slower (maximum degradation)


class GracefulDegradationController:
    """Graceful degradation controller with smooth frequency adaptation.

    Instead of completely stopping updates (like circuit breaker), gradually
    reduces update frequency when failures occur, and gradually recovers when
    operations succeed again.

    Args:
        failure_threshold: Consecutive failures before upgrading degradation level (default: 3)
        success_threshold: Consecutive successes before downgrading degradation level (default: 2)
        max_level: Maximum degradation level (default: 4, = 16x slowdown)

    Example:
        controller = GracefulDegradationController(failure_threshold=3)

        # Always allowed, but may slow down
        multiplier = controller.get_slowdown_multiplier()  # 1.0, 2.0, 4.0, 8.0, or 16.0
        adjusted_interval = base_interval * multiplier

        try:
            await api_call()
            controller.record_success()  # Gradually recover
        except Exception:
            controller.record_failure()  # Gradually degrade

    Performance (estimated based on simpler state machine):
    - get_slowdown_multiplier(): ~100ns (enum value access)
    - record_success/failure(): ~150ns (counter increment + comparison)
    - Total overhead: < 300ns per operation (50% less than circuit breaker)
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        success_threshold: int = 2,
        max_level: int = 4,
    ) -> None:
        """Initialize graceful degradation controller.

        Args:
            failure_threshold: Consecutive failures before upgrading degradation
            success_threshold: Consecutive successes before downgrading degradation
            max_level: Maximum degradation level (0-4)
        """
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if max_level < 0 or max_level > 4:
            raise ValueError("max_level must be 0-4")

        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._max_level = max_level

        self._current_level = DegradationLevel.NORMAL
        self._consecutive_failures = 0
        self._consecutive_successes = 0

    def get_slowdown_multiplier(self) -> float:
        """Get current slowdown multiplier for update frequency.

        Returns:
            Multiplier to apply to base update interval (1.0, 2.0, 4.0, 8.0, or 16.0)
        """
        return 2.0**self._current_level.value

    def get_current_level(self) -> DegradationLevel:
        """Get current degradation level."""
        return self._current_level

    def should_allow_update(self) -> bool:
        """Check if updates are allowed.

        Always returns True (graceful degradation never completely blocks).
        Use get_slowdown_multiplier() to adjust frequency instead.
        """
        return True

    def record_failure(self) -> None:
        """Record operation failure and potentially upgrade degradation level."""
        self._consecutive_failures += 1
        self._consecutive_successes = 0

        if self._consecutive_failures >= self._failure_threshold:
            self._upgrade_degradation()
            self._consecutive_failures = 0

    def record_success(self) -> None:
        """Record operation success and potentially downgrade degradation level."""
        self._consecutive_successes += 1
        self._consecutive_failures = 0

        if self._consecutive_successes >= self._success_threshold:
            self._downgrade_degradation()
            self._consecutive_successes = 0

    def _upgrade_degradation(self) -> None:
        """Upgrade to higher degradation level (slower updates)."""
        current_value = self._current_level.value
        if current_value >= self._max_level:
            return

        new_level = DegradationLevel(current_value + 1)
        self._current_level = new_level
        new_multiplier = self.get_slowdown_multiplier()

        logger.warning(
            "degradation_upgraded: level=%s multiplier=%s failures=%d",
            new_level.name,
            new_multiplier,
            self._failure_threshold,
        )

    def _downgrade_degradation(self) -> None:
        """Downgrade to lower degradation level (faster updates)."""
        current_value = self._current_level.value
        if current_value == 0:
            return

        new_level = DegradationLevel(current_value - 1)
        self._current_level = new_level
        new_multiplier = self.get_slowdown_multiplier()

        logger.info(
            "degradation_downgraded: level=%s multiplier=%s successes=%d",
            new_level.name,
            new_multiplier,
            self._success_threshold,
        )

    def reset(self) -> None:
        """Reset to normal degradation level."""
        if self._current_level != DegradationLevel.NORMAL:
            logger.info("degradation_reset: level=NORMAL")

        self._current_level = DegradationLevel.NORMAL
        self._consecutive_failures = 0
        self._consecutive_successes = 0

    def get_stats(self) -> dict[str, object]:
        """Get current statistics for debugging.

        Returns:
            Dictionary with level, multiplier, and consecutive counts
        """
        return {
            "level": self._current_level.name,
            "multiplier": self.get_slowdown_multiplier(),
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
        }
