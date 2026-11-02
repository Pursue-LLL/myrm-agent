"""The diagnostic SLO counts a run as failed unless it is ready or missing (an optional capability that is off)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.services.memory.diagnostics.diagnostic.diagnostic_slo import build_diagnostic_slo
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService


def _run_event(diagnostic_status: str | None, *, event_status: str = "success") -> SimpleNamespace:
    metadata = {"duration_ms": 100.0}
    if diagnostic_status is not None:
        metadata["diagnostic_status"] = diagnostic_status
    return SimpleNamespace(source="memory_diagnostics", target_id="diagnostic_run", status=event_status, metadata_json=metadata)


def _ledger(*events: SimpleNamespace) -> MemoryOperationLedgerService:
    return cast(MemoryOperationLedgerService, SimpleNamespace(list_events=AsyncMock(return_value=list(events))))


@pytest.mark.asyncio
async def test_slo_is_missing_without_any_diagnostic_run() -> None:
    slo = await build_diagnostic_slo(_ledger())

    assert (slo.window_runs, slo.status) == (0, "missing")


@pytest.mark.asyncio
async def test_slo_stays_ready_when_every_run_is_missing() -> None:
    slo = await build_diagnostic_slo(_ledger(*[_run_event("missing") for _ in range(3)]))

    assert (slo.window_runs, slo.failed_runs, slo.pass_rate, slo.status) == (3, 0, 1.0, "ready")


@pytest.mark.asyncio
async def test_slo_still_counts_critical_and_warning_runs_as_failed() -> None:
    events = [_run_event("missing")] * 6 + [_run_event("critical")] * 2 + [_run_event("warning")] * 2

    slo = await build_diagnostic_slo(_ledger(*events))

    assert (slo.failed_runs, slo.pass_rate, slo.status) == (4, 0.6, "critical")


@pytest.mark.asyncio
async def test_slo_thresholds_apply_to_the_failed_share() -> None:
    warning = await build_diagnostic_slo(_ledger(*[_run_event("ready")] * 8, *[_run_event("critical")] * 2))
    ready = await build_diagnostic_slo(_ledger(*[_run_event("missing")] * 19, _run_event("critical")))

    assert (warning.pass_rate, warning.status) == (0.8, "warning")
    assert (ready.pass_rate, ready.status) == (0.95, "ready")


@pytest.mark.asyncio
async def test_slo_counts_a_run_without_a_diagnostic_status_by_its_event_status() -> None:
    slo = await build_diagnostic_slo(_ledger(_run_event(None, event_status="error")))

    assert (slo.failed_runs, slo.status) == (1, "critical")
