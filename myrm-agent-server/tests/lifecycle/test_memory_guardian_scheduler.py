"""Tests for memory_guardian scheduler wiring to pattern discovery.

Covers the three links between the guardian scheduler and the pattern
discovery trigger that the trigger-level tests do not reach:

1. ``run_pattern_discovery_once`` delegation transparency
2. ``_run_pattern_discovery_cycle`` delegation (the 168h periodic entry)
3. ``_pattern_discovery_due`` — the extracted weekly-gate predicate

None of these drive the infinite background loop; the loop logic itself is
covered by the pure predicate plus the two thin delegation functions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.lifecycle import memory_guardian


@pytest.fixture(autouse=True)
def _reset_scheduler_state() -> None:
    """Keep module globals deterministic across tests."""
    memory_guardian._last_pattern_discovery = 0.0
    memory_guardian._scheduler_task = None
    memory_guardian._next_run = None
    memory_guardian._last_run = None
    memory_guardian._consecutive_unhealthy = 0
    yield
    memory_guardian._scheduler_task = None


class TestPatternDiscoveryDelegation:
    """The manual-trigger API entry must transparently forward to the trigger module."""

    @pytest.mark.asyncio
    async def test_run_pattern_discovery_once_forwards_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {
            "triggered": True,
            "skipped": True,
            "reason": "memory system not yet mature enough",
        }
        trigger = MagicMock()
        trigger.run_pattern_discovery_once = AsyncMock(return_value=payload)
        monkeypatch.setattr(
            "app.lifecycle.pattern_discovery_trigger.run_pattern_discovery_once",
            trigger.run_pattern_discovery_once,
        )

        result = await memory_guardian.run_pattern_discovery_once()

        trigger.run_pattern_discovery_once.assert_awaited_once_with()
        assert result == payload

    @pytest.mark.asyncio
    async def test_run_pattern_discovery_once_propagates_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        trigger = MagicMock()
        trigger.run_pattern_discovery_once = AsyncMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(
            "app.lifecycle.pattern_discovery_trigger.run_pattern_discovery_once",
            trigger.run_pattern_discovery_once,
        )

        with pytest.raises(RuntimeError, match="boom"):
            await memory_guardian.run_pattern_discovery_once()


class TestPatternDiscoveryCycleDelegation:
    """The 168h periodic entry must delegate to the trigger module and swallow nothing."""

    @pytest.mark.asyncio
    async def test_cycle_delegates_to_trigger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []

        async def fake_cycle() -> None:
            called.append("cyc")

        monkeypatch.setattr(
            "app.lifecycle.pattern_discovery_trigger.run_pattern_discovery_cycle",
            fake_cycle,
        )

        await memory_guardian._run_pattern_discovery_cycle()

        assert called == ["cyc"]


class TestPatternDiscoveryDue:
    """Weekly-gate predicate extracted from the guardian loop."""

    def test_not_due_within_interval(self) -> None:
        now = 1_000_000.0
        # 167h since last run → 0.99 of the weekly interval.
        last = now - 167 * 3600
        assert memory_guardian._pattern_discovery_due(now=now, last=last) is False

    def test_due_at_exact_boundary(self) -> None:
        now = 1_000_000.0
        last = now - 168 * 3600
        assert memory_guardian._pattern_discovery_due(now=now, last=last) is True

    def test_due_after_interval(self) -> None:
        now = 1_000_000.0
        last = now - (168 * 3600 + 60)
        assert memory_guardian._pattern_discovery_due(now=now, last=last) is True

    def test_due_when_never_ran(self) -> None:
        now = 1_000_000.0
        assert memory_guardian._pattern_discovery_due(now=now, last=0.0) is True

    def test_due_non_default_interval(self) -> None:
        now = 1_000_000.0
        last = now - 25 * 3600
        assert memory_guardian._pattern_discovery_due(now=now, last=last, interval_hours=24) is True
        assert memory_guardian._pattern_discovery_due(now=now, last=last, interval_hours=26) is False
