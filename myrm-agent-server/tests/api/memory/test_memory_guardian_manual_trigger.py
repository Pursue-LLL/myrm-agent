"""Tests for manual memory guardian trigger."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.lifecycle import memory_guardian


def _make_report(
    *,
    skipped: bool = False,
    forgotten: int = 0,
    archived: int = 0,
    merged: int = 0,
    corrected: int = 0,
    health_total: int = 85,
) -> SimpleNamespace:
    return SimpleNamespace(
        skipped=skipped,
        skip_reason="ok" if skipped else None,
        forgotten_count=forgotten,
        archived_count=archived,
        consolidation_merged=merged,
        consolidation_corrected=corrected,
        duration_ms=100.0,
        health=SimpleNamespace(total=health_total, to_dict=lambda: {"total": health_total}),
    )


class TestManualMemoryGuardianTrigger:
    @pytest.mark.asyncio
    async def test_run_memory_guardian_once_forces_maintenance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        report = _make_report(skipped=True)
        manager = AsyncMock()
        manager.run_maintenance_cycle.return_value = report
        manager.compute_health_score = AsyncMock()

        create_manager = AsyncMock(return_value=manager)
        monkeypatch.setattr(memory_guardian, "_create_memory_manager", create_manager)
        run_cycle = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_run_guardian_cycle", run_cycle)

        result = await memory_guardian.run_memory_guardian_once()

        assert result == {"triggered": True, "health": {"total": 85}}
        create_manager.assert_awaited_once()
        manager.run_maintenance_cycle.assert_awaited_once_with(force=True)
        manager.compute_health_score.assert_not_awaited()
        run_cycle.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_memory_guardian_once_records_audit_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        report = _make_report(forgotten=3, merged=1)
        manager = AsyncMock()
        manager.run_maintenance_cycle.return_value = report

        monkeypatch.setattr(memory_guardian, "_create_memory_manager", AsyncMock(return_value=manager))
        record_fn = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_record_maintenance_event", record_fn)

        result = await memory_guardian.run_memory_guardian_once()

        assert result["triggered"] is True
        record_fn.assert_awaited_once_with(report, forced=True)

    @pytest.mark.asyncio
    async def test_run_memory_guardian_once_skips_audit_when_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        report = _make_report(skipped=True)
        manager = AsyncMock()
        manager.run_maintenance_cycle.return_value = report

        monkeypatch.setattr(memory_guardian, "_create_memory_manager", AsyncMock(return_value=manager))
        record_fn = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_record_maintenance_event", record_fn)

        await memory_guardian.run_memory_guardian_once()

        record_fn.assert_not_awaited()
