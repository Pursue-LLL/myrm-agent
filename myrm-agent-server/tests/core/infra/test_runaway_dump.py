"""Tests for RunawayDumper: sustained breach, cooldown, bounded reports, and retention."""

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.core.infra.runaway_dump import RunawayDumper, RunawayThresholds


@dataclass
class _Sample:
    cpu_percent: float


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _reports(log_dir: Path) -> list[Path]:
    return sorted(log_dir.glob("runaway-*.txt"))


def test_from_settings_uses_the_data_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Database:
        state_dir = str(tmp_path)

    class _Settings:
        database = _Database()

    monkeypatch.setattr("app.config.settings.settings", _Settings())

    dumper = RunawayDumper.from_settings()

    assert dumper._log_dir == tmp_path / "logs"


def test_sustained_cpu_breach_writes_a_report(tmp_path: Path) -> None:
    clock = _Clock()
    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(cpu_percent=50.0, cpu_samples=2, thread_count=10_000),
        clock=clock,
    )

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=95.0))
        assert not _reports(tmp_path)
        await dumper.on_metrics(_Sample(cpu_percent=95.0))

    asyncio.run(run())

    reports = _reports(tmp_path)
    assert len(reports) == 1
    content = reports[0].read_text(encoding="utf-8")
    assert "== asyncio tasks ==" in content
    assert "== threads (identical stacks aggregated) ==" in content


def test_one_high_sample_is_not_enough(tmp_path: Path) -> None:
    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(cpu_percent=50.0, cpu_samples=3, thread_count=10_000),
        clock=_Clock(),
    )

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=95.0))
        await dumper.on_metrics(_Sample(cpu_percent=20.0))
        await dumper.on_metrics(_Sample(cpu_percent=95.0))

    asyncio.run(run())
    assert _reports(tmp_path) == []


def test_thread_breach_triggers_and_cooldown_suppresses_repeats(tmp_path: Path) -> None:
    clock = _Clock()
    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(thread_count=0, thread_samples=1, cpu_percent=1000.0, cooldown_sec=600.0),
        clock=clock,
    )

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=1.0))
        assert len(_reports(tmp_path)) == 1
        clock.now += 10.0
        await dumper.on_metrics(_Sample(cpu_percent=1.0))

    asyncio.run(run())
    assert len(_reports(tmp_path)) == 1


def test_write_failure_is_swallowed_and_attempts_are_not_stuck(tmp_path: Path) -> None:
    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(thread_count=0, thread_samples=1, cpu_percent=1000.0),
        clock=_Clock(),
    )

    def explode(*args: object) -> None:
        raise OSError("disk full")

    dumper._write_report = explode  # type: ignore[method-assign]

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=1.0))

    asyncio.run(run())
    assert dumper._writing is False


def test_overlapping_sample_is_ignored(tmp_path: Path) -> None:
    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(thread_count=0, thread_samples=1, cpu_percent=1000.0),
        clock=_Clock(),
    )
    dumper._writing = True

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=1.0))

    asyncio.run(run())
    assert _reports(tmp_path) == []


def test_identical_stacks_are_aggregated(tmp_path: Path) -> None:
    release = threading.Event()

    def worker() -> None:
        release.wait(2.0)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()

    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(thread_count=0, thread_samples=1, cpu_percent=1000.0),
        clock=_Clock(),
    )

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=1.0))

    try:
        asyncio.run(run())
    finally:
        release.set()
        for thread in threads:
            thread.join(2.0)

    content = _reports(tmp_path)[0].read_text(encoding="utf-8")
    assert "-- 2 thread(s):" in content


def test_report_is_truncated_at_the_byte_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.infra import runaway_dump

    monkeypatch.setattr(runaway_dump, "_MAX_REPORT_BYTES", 40)
    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(thread_count=0, thread_samples=1, cpu_percent=1000.0),
        clock=_Clock(),
    )

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=1.0))

    asyncio.run(run())

    content = _reports(tmp_path)[0].read_text(encoding="utf-8")
    assert content.endswith("... report truncated")


def test_retention_keeps_only_the_newest_three_reports(tmp_path: Path) -> None:
    for index in range(5):
        (tmp_path / f"runaway-2026010{index}-120000-1.txt").write_text("old", encoding="utf-8")
    dumper = RunawayDumper(
        tmp_path,
        RunawayThresholds(thread_count=0, thread_samples=1, cpu_percent=1000.0),
        clock=_Clock(),
    )

    async def run() -> None:
        await dumper.on_metrics(_Sample(cpu_percent=1.0))

    asyncio.run(run())

    reports = _reports(tmp_path)
    assert len(reports) == 3
    assert reports[-1].read_text(encoding="utf-8").startswith("runaway report at")
