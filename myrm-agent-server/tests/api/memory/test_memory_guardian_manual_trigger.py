"""Tests for manual memory guardian trigger."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.lifecycle import memory_guardian
from app.services.memory.guardian_policy import MemoryGuardianPolicy


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
    async def test_run_memory_guardian_once_force_mode_executes_forced_cycle(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _make_report(skipped=False)
        run_cycle = AsyncMock(return_value=(report, None))
        monkeypatch.setattr(memory_guardian, "_run_guardian_cycle", run_cycle)

        result = await memory_guardian.run_memory_guardian_once(mode="force")

        assert result == {
            "triggered": True,
            "mode": "force",
            "applied": True,
            "health": {"total": 85},
        }
        run_cycle.assert_awaited_once_with(force=True)

    @pytest.mark.asyncio
    async def test_run_memory_guardian_once_safe_mode_surfaces_skip_reason(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_cycle = AsyncMock(return_value=(None, "active_sessions"))
        monkeypatch.setattr(memory_guardian, "_run_guardian_cycle", run_cycle)

        result = await memory_guardian.run_memory_guardian_once()

        assert result == {
            "triggered": True,
            "mode": "safe",
            "applied": False,
            "skipped_reason": "active_sessions",
        }
        run_cycle.assert_awaited_once_with(force=False)

    @pytest.mark.asyncio
    async def test_run_memory_guardian_once_keeps_report_health_when_skipped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _make_report(skipped=True)
        run_cycle = AsyncMock(return_value=(report, "maintenance_skipped"))
        monkeypatch.setattr(memory_guardian, "_run_guardian_cycle", run_cycle)

        result = await memory_guardian.run_memory_guardian_once(mode="safe")

        assert result["applied"] is False
        assert result["skipped_reason"] == "maintenance_skipped"
        assert result["health"] == {"total": 85}

    @pytest.mark.asyncio
    async def test_run_guardian_cycle_force_bypasses_guards_and_runs_maintenance(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _make_report(forgotten=3, merged=1)
        manager = AsyncMock()
        manager.run_maintenance_cycle.return_value = report

        monkeypatch.setattr(memory_guardian, "_create_memory_manager", AsyncMock(return_value=manager))
        monkeypatch.setattr(memory_guardian, "_record_maintenance_event", AsyncMock())
        monkeypatch.setattr(memory_guardian, "_persist_health_snapshot", AsyncMock())
        monkeypatch.setattr(memory_guardian, "_purge_expired_archives", AsyncMock(return_value=0))
        monkeypatch.setattr(memory_guardian, "_record_purge_audit", AsyncMock())
        monkeypatch.setattr(memory_guardian, "_auto_resolve_expired_conflicts", AsyncMock(return_value=0))
        monkeypatch.setattr(memory_guardian, "_run_sqlite_backup", lambda: None)

        cycle_report, skipped_reason = await memory_guardian._run_guardian_cycle(
            force=True,
            policy=MemoryGuardianPolicy(),
        )

        assert skipped_reason is None
        assert cycle_report is report
        manager.run_maintenance_cycle.assert_awaited_once_with(force=True)

    @pytest.mark.asyncio
    async def test_run_guardian_cycle_safe_respects_quiet_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(memory_guardian, "is_within_quiet_window", lambda *, policy: False)
        create_manager = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_create_memory_manager", create_manager)

        cycle_report, skipped_reason = await memory_guardian._run_guardian_cycle(
            force=False,
            policy=MemoryGuardianPolicy(
                quiet_window_enabled=True,
                quiet_window_start_hour=0,
                quiet_window_end_hour=6,
            ),
        )

        assert cycle_report is None
        assert skipped_reason == "outside_quiet_window"
        create_manager.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_guardian_cycle_safe_fails_closed_when_active_session_guard_unavailable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise_gateway() -> SimpleNamespace:
            raise RuntimeError("gateway unavailable")

        monkeypatch.setattr("app.services.agent.gateway.get_agent_gateway", _raise_gateway)
        create_manager = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_create_memory_manager", create_manager)
        warning_event = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_record_guard_unavailable_event", warning_event)

        cycle_report, skipped_reason = await memory_guardian._run_guardian_cycle(
            force=False,
            policy=MemoryGuardianPolicy(),
        )

        assert cycle_report is None
        assert skipped_reason == "active_session_guard_unavailable"
        create_manager.assert_not_called()
        warning_event.assert_awaited_once()
        assert warning_event.await_args.kwargs["reason"] == "active_session_guard_unavailable"
        assert warning_event.await_args.kwargs["guard"] == "active_session"

    @pytest.mark.asyncio
    async def test_run_guardian_cycle_safe_fails_closed_when_budget_guard_unavailable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.agent.gateway.get_agent_gateway",
            lambda: SimpleNamespace(active_count=0),
        )

        async def _raise_budget() -> bool:
            raise RuntimeError("budget unavailable")

        monkeypatch.setattr("app.services.budget.enforcer.should_block_execution", _raise_budget)
        create_manager = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_create_memory_manager", create_manager)
        warning_event = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_record_guard_unavailable_event", warning_event)

        cycle_report, skipped_reason = await memory_guardian._run_guardian_cycle(
            force=False,
            policy=MemoryGuardianPolicy(),
        )

        assert cycle_report is None
        assert skipped_reason == "budget_guard_unavailable"
        create_manager.assert_not_called()
        warning_event.assert_awaited_once()
        assert warning_event.await_args.kwargs["reason"] == "budget_guard_unavailable"
        assert warning_event.await_args.kwargs["guard"] == "budget"

    @pytest.mark.asyncio
    async def test_run_guardian_cycle_safe_fails_closed_when_capacity_guard_unavailable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.agent.gateway.get_agent_gateway",
            lambda: SimpleNamespace(active_count=0),
        )

        async def _allow_budget() -> bool:
            return False

        def _raise_capacity_guard() -> object:
            raise RuntimeError("capacity scheduler unavailable")

        monkeypatch.setattr("app.services.budget.enforcer.should_block_execution", _allow_budget)
        monkeypatch.setattr(
            "myrm_agent_harness.runtime.maintenance.scheduler.get_maintenance_scheduler",
            _raise_capacity_guard,
        )
        create_manager = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_create_memory_manager", create_manager)
        warning_event = AsyncMock()
        monkeypatch.setattr(memory_guardian, "_record_guard_unavailable_event", warning_event)

        cycle_report, skipped_reason = await memory_guardian._run_guardian_cycle(
            force=False,
            policy=MemoryGuardianPolicy(),
        )

        assert cycle_report is None
        assert skipped_reason == "capacity_guard_unavailable"
        create_manager.assert_not_called()
        warning_event.assert_awaited_once()
        assert warning_event.await_args.kwargs["reason"] == "capacity_guard_unavailable"
        assert warning_event.await_args.kwargs["guard"] == "capacity"

    @pytest.mark.asyncio
    async def test_record_guard_unavailable_event_enqueues_control_plane_telemetry(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        enqueue_mock = MagicMock()
        monkeypatch.setattr(
            "app.services.agent.memory_guardian_guard_telemetry.enqueue_memory_guardian_guard_telemetry",
            enqueue_mock,
        )

        @asynccontextmanager
        async def _fake_session():
            yield AsyncMock()

        monkeypatch.setattr("app.database.connection.get_session", lambda: _fake_session())
        record_event_mock = AsyncMock()
        monkeypatch.setattr(
            "app.services.memory.operation_ledger.MemoryOperationLedgerService.record_event",
            record_event_mock,
        )

        policy = MemoryGuardianPolicy(
            frequency_tier="aggressive",
            quiet_window_enabled=True,
            quiet_window_start_hour=22,
            quiet_window_end_hour=6,
        )

        await memory_guardian._record_guard_unavailable_event(
            reason="budget_guard_unavailable",
            guard="budget",
            policy=policy,
        )

        enqueue_mock.assert_called_once_with(
            reason="budget_guard_unavailable",
            guard="budget",
            frequency_tier="aggressive",
            quiet_window_enabled=True,
        )
        record_event_mock.assert_awaited_once()
