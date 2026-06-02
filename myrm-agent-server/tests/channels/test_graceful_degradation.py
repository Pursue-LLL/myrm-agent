"""Unit tests for graceful degradation controller."""

import pytest

from app.channels.routing.graceful_degradation import (
    DegradationLevel,
    GracefulDegradationController,
)


class TestGracefulDegradationController:
    """Test suite for graceful degradation controller."""

    def test_initial_state_normal(self) -> None:
        """Controller starts at NORMAL level."""
        controller = GracefulDegradationController()

        assert controller.get_current_level() == DegradationLevel.NORMAL
        assert controller.get_slowdown_multiplier() == 1.0
        assert controller.should_allow_update() is True

    def test_always_allows_updates(self) -> None:
        """Graceful degradation never completely blocks updates."""
        controller = GracefulDegradationController(failure_threshold=1, max_level=4)

        for _ in range(10):
            controller.record_failure()

        assert controller.should_allow_update() is True

    def test_upgrade_on_consecutive_failures(self) -> None:
        """Upgrades degradation level after consecutive failures."""
        controller = GracefulDegradationController(failure_threshold=3)

        assert controller.get_current_level() == DegradationLevel.NORMAL

        controller.record_failure()
        controller.record_failure()
        assert controller.get_current_level() == DegradationLevel.NORMAL

        controller.record_failure()
        assert controller.get_current_level() == DegradationLevel.DEGRADED_1
        assert controller.get_slowdown_multiplier() == 2.0

    def test_downgrade_on_consecutive_successes(self) -> None:
        """Downgrades degradation level after consecutive successes."""
        controller = GracefulDegradationController(failure_threshold=2, success_threshold=2)

        for _ in range(2):
            controller.record_failure()
        assert controller.get_current_level() == DegradationLevel.DEGRADED_1

        controller.record_success()
        assert controller.get_current_level() == DegradationLevel.DEGRADED_1

        controller.record_success()
        assert controller.get_current_level() == DegradationLevel.NORMAL
        assert controller.get_slowdown_multiplier() == 1.0

    def test_success_resets_failure_counter(self) -> None:
        """Success resets consecutive failure counter."""
        controller = GracefulDegradationController(failure_threshold=3)

        controller.record_failure()
        controller.record_failure()
        controller.record_success()
        controller.record_failure()
        controller.record_failure()

        assert controller.get_current_level() == DegradationLevel.NORMAL

    def test_failure_resets_success_counter(self) -> None:
        """Failure resets consecutive success counter."""
        controller = GracefulDegradationController(failure_threshold=2, success_threshold=3)

        for _ in range(2):
            controller.record_failure()
        assert controller.get_current_level() == DegradationLevel.DEGRADED_1

        controller.record_success()
        controller.record_success()
        controller.record_failure()
        controller.record_success()

        assert controller.get_current_level() == DegradationLevel.DEGRADED_1

    def test_max_degradation_level(self) -> None:
        """Degradation does not exceed max_level."""
        controller = GracefulDegradationController(failure_threshold=1, max_level=4)

        for _ in range(10):
            controller.record_failure()

        assert controller.get_current_level() == DegradationLevel.DEGRADED_4
        assert controller.get_slowdown_multiplier() == 16.0

    def test_slowdown_multiplier_exponential(self) -> None:
        """Slowdown multiplier grows exponentially with level."""
        controller = GracefulDegradationController(failure_threshold=1)

        multipliers = []
        for _i in range(5):
            multipliers.append(controller.get_slowdown_multiplier())
            controller.record_failure()

        assert multipliers == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_reset_to_normal(self) -> None:
        """Reset clears all state and returns to NORMAL."""
        controller = GracefulDegradationController(failure_threshold=1)

        for _ in range(3):
            controller.record_failure()
        assert controller.get_current_level() == DegradationLevel.DEGRADED_3

        controller.reset()

        assert controller.get_current_level() == DegradationLevel.NORMAL
        assert controller.get_slowdown_multiplier() == 1.0

        stats = controller.get_stats()
        assert stats["consecutive_failures"] == 0
        assert stats["consecutive_successes"] == 0

    def test_get_stats(self) -> None:
        """get_stats returns current controller state."""
        controller = GracefulDegradationController(failure_threshold=2)

        controller.record_failure()

        stats = controller.get_stats()
        assert stats["level"] == "NORMAL"
        assert stats["multiplier"] == 1.0
        assert stats["consecutive_failures"] == 1
        assert stats["consecutive_successes"] == 0

    def test_invalid_failure_threshold(self) -> None:
        """Raises error for invalid failure_threshold."""
        with pytest.raises(ValueError, match="failure_threshold must be >= 1"):
            GracefulDegradationController(failure_threshold=0)

    def test_invalid_success_threshold(self) -> None:
        """Raises error for invalid success_threshold."""
        with pytest.raises(ValueError, match="success_threshold must be >= 1"):
            GracefulDegradationController(success_threshold=0)

    def test_invalid_max_level(self) -> None:
        """Raises error for invalid max_level."""
        with pytest.raises(ValueError, match="max_level must be 0-4"):
            GracefulDegradationController(max_level=5)

        with pytest.raises(ValueError, match="max_level must be 0-4"):
            GracefulDegradationController(max_level=-1)
