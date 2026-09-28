"""Memory-pressure gate tests for the cron agent runner."""

from __future__ import annotations

import pytest

from app.core.cron.adapters.agent_runner import (
    AgentJobRunner,
    _memory_overload_reason,
)


class _FakeLevel:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeMonitor:
    def __init__(self, level: str) -> None:
        self.current_level = _FakeLevel(level)


def _patch_monitor(monkeypatch: pytest.MonkeyPatch, level: str | None) -> None:
    import app.lifecycle.monitors as monitors_module

    if level is None:
        monkeypatch.setattr(monitors_module, "_memory_pressure_monitor", None)
    else:
        monkeypatch.setattr(
            monitors_module, "_memory_pressure_monitor", _FakeMonitor(level)
        )


def test_overload_reason_none_when_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_monitor(monkeypatch, "NORMAL")
    assert _memory_overload_reason() is None


def test_overload_reason_none_when_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_monitor(monkeypatch, "WARNING")
    assert _memory_overload_reason() is None


def test_overload_reason_set_when_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_monitor(monkeypatch, "CRITICAL")
    assert _memory_overload_reason() == "memory_pressure:critical"


def test_overload_reason_set_when_emergency(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_monitor(monkeypatch, "EMERGENCY")
    assert _memory_overload_reason() == "memory_pressure:emergency"


def test_overload_reason_none_when_monitor_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_monitor(monkeypatch, None)
    assert _memory_overload_reason() is None


def test_overload_reason_fail_open_on_probe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.lifecycle.monitors as monitors_module

    class _BrokenMonitor:
        @property
        def current_level(self):  # noqa: ANN202
            raise RuntimeError("sensor dead")

    monkeypatch.setattr(monitors_module, "_memory_pressure_monitor", _BrokenMonitor())
    assert _memory_overload_reason() is None


@pytest.mark.asyncio
async def test_run_skips_without_consuming_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from myrm_agent_harness.toolkits.cron import types as cron_types

    import app.lifecycle.monitors as monitors_module

    monkeypatch.setattr(
        monitors_module, "_memory_pressure_monitor", _FakeMonitor("CRITICAL")
    )
    runner = AgentJobRunner()
    attempts = 0

    async def _never_runs(job, *, context=""):  # noqa: ANN001, ANN202
        nonlocal attempts
        attempts += 1
        raise AssertionError("must not execute under memory pressure")

    monkeypatch.setattr(runner, "_run_once", _never_runs)
    job = cron_types.CronJob(
        id="job-1",
        user_id="default",
        name="ping",
        job_type=cron_types.JobType.AGENT,
        schedule=cron_types.Schedule(kind=cron_types.ScheduleKind.INTERVAL, interval_ms=3_600_000),
        prompt="ping",
    )
    result = await runner.run(job)
    assert result.skipped is True
    assert result.skip_reason == "memory_pressure:critical"
    assert result.success is False
    assert attempts == 0
