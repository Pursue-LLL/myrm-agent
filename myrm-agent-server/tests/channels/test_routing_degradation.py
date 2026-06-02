"""GracefulDegradationController tests — levels, thresholds, reset."""

from __future__ import annotations

import pytest

from app.channels.routing.graceful_degradation import (
    DegradationLevel,
    GracefulDegradationController,
)


class TestDegradationLevel:
    def test_enum_values(self) -> None:
        assert DegradationLevel.NORMAL.value == 0
        assert DegradationLevel.DEGRADED_4.value == 4


class TestGracefulDegradationInit:
    def test_defaults(self) -> None:
        ctrl = GracefulDegradationController()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL
        assert ctrl.get_slowdown_multiplier() == 1.0

    def test_invalid_failure_threshold(self) -> None:
        with pytest.raises(ValueError, match="failure_threshold"):
            GracefulDegradationController(failure_threshold=0)

    def test_invalid_success_threshold(self) -> None:
        with pytest.raises(ValueError, match="success_threshold"):
            GracefulDegradationController(success_threshold=0)

    def test_invalid_max_level_low(self) -> None:
        with pytest.raises(ValueError, match="max_level"):
            GracefulDegradationController(max_level=-1)

    def test_invalid_max_level_high(self) -> None:
        with pytest.raises(ValueError, match="max_level"):
            GracefulDegradationController(max_level=5)


class TestDegradationBehavior:
    def test_should_allow_update_always_true(self) -> None:
        ctrl = GracefulDegradationController()
        assert ctrl.should_allow_update() is True
        for _ in range(20):
            ctrl.record_failure()
        assert ctrl.should_allow_update() is True

    def test_failure_upgrades_level(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=2)
        ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL
        ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.DEGRADED_1
        assert ctrl.get_slowdown_multiplier() == 2.0

    def test_success_downgrades_level(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=1, success_threshold=1)
        ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.DEGRADED_1
        ctrl.record_success()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL

    def test_max_level_capped(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=1, max_level=2)
        for _ in range(10):
            ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.DEGRADED_2
        assert ctrl.get_slowdown_multiplier() == 4.0

    def test_cannot_downgrade_below_normal(self) -> None:
        ctrl = GracefulDegradationController(success_threshold=1)
        ctrl.record_success()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL

    def test_failure_resets_success_counter(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=2, success_threshold=2)
        ctrl.record_failure()
        ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.DEGRADED_1
        ctrl.record_success()
        ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.DEGRADED_1

    def test_success_resets_failure_counter(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=3)
        ctrl.record_failure()
        ctrl.record_failure()
        ctrl.record_success()
        ctrl.record_failure()
        ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL

    def test_full_degradation_and_recovery(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=1, success_threshold=1, max_level=4)
        for _ in range(4):
            ctrl.record_failure()
        assert ctrl.get_current_level() == DegradationLevel.DEGRADED_4
        assert ctrl.get_slowdown_multiplier() == 16.0

        for _ in range(4):
            ctrl.record_success()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL
        assert ctrl.get_slowdown_multiplier() == 1.0


class TestDegradationReset:
    def test_reset_from_degraded(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=1)
        ctrl.record_failure()
        ctrl.record_failure()
        assert ctrl.get_current_level() != DegradationLevel.NORMAL
        ctrl.reset()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL

    def test_reset_from_normal(self) -> None:
        ctrl = GracefulDegradationController()
        ctrl.reset()
        assert ctrl.get_current_level() == DegradationLevel.NORMAL


class TestDegradationStats:
    def test_get_stats(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=2)
        ctrl.record_failure()
        stats = ctrl.get_stats()
        assert stats["level"] == "NORMAL"
        assert stats["multiplier"] == 1.0
        assert stats["consecutive_failures"] == 1
        assert stats["consecutive_successes"] == 0

    def test_get_stats_after_upgrade(self) -> None:
        ctrl = GracefulDegradationController(failure_threshold=1)
        ctrl.record_failure()
        stats = ctrl.get_stats()
        assert stats["level"] == "DEGRADED_1"
        assert stats["multiplier"] == 2.0
