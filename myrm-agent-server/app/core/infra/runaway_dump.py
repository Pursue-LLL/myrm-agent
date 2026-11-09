"""[INPUT]
- myrm_agent_harness.runtime.survival.resource_monitor::ResourceMetrics (POS: Resource usage metrics)

[OUTPUT]
- RunawayDumper: 持续超阈值时落盘线程栈与 asyncio 任务栈

[POS]
失控现场采集器。进程空转无法事后剖析，只能在发生时抓栈；该监听器复用资源采样，
持续超阈值后写入 ``<数据目录>/logs/runaway-*.txt``。只记录，不取消任何工作。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Protocol

logger = logging.getLogger(__name__)

_MAX_THREAD_SAMPLES = 200
_MAX_FRAMES_PER_STACK = 40
_KEEP_REPORTS = 3
_MAX_REPORT_BYTES = 2 * 1024 * 1024


class _Sample(Protocol):
    """The slice of the harness resource metrics this listener needs."""

    cpu_percent: float


@dataclass(frozen=True)
class RunawayThresholds:
    """Sustained breach required before a dump; one noisy sample is not enough."""

    thread_count: int = 200
    cpu_percent: float = 90.0
    thread_samples: int = 3
    cpu_samples: int = 6
    cooldown_sec: float = 600.0


class RunawayDumper:
    """Write an on-disk flight recorder once a sustained resource breach is observed."""

    def __init__(
        self,
        log_dir: Path,
        thresholds: RunawayThresholds | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._log_dir = log_dir
        self._thresholds = thresholds or RunawayThresholds()
        self._clock = clock
        self._thread_hits = 0
        self._cpu_hits = 0
        self._last_dump = 0.0
        self._writing = False

    @classmethod
    def from_settings(cls) -> RunawayDumper:
        """Build the dumper against the configured data directory."""
        from app.config.settings import settings

        return cls(Path(settings.database.state_dir).expanduser() / "logs")

    async def on_metrics(self, metrics: _Sample) -> None:
        """Resource monitor listener: count breaches, then dump once per cooldown."""
        if self._writing:
            return

        self._thread_hits = self._thread_hits + 1 if threading.active_count() > self._thresholds.thread_count else 0
        self._cpu_hits = self._cpu_hits + 1 if metrics.cpu_percent > self._thresholds.cpu_percent else 0

        triggered = self._thread_hits >= self._thresholds.thread_samples or self._cpu_hits >= self._thresholds.cpu_samples
        now = self._clock()
        if not triggered or now - self._last_dump < self._thresholds.cooldown_sec:
            return

        self._last_dump = now
        self._thread_hits = 0
        self._cpu_hits = 0
        self._writing = True
        try:
            # Only the asyncio task list must be read on the loop; rendering thousands of thread
            # stacks is CPU-heavy and belongs on a worker.
            task_lines = self._asyncio_task_lines()
            frames = sys._current_frames()
            threads = {item.ident: f"{item.name} (daemon={item.daemon})" for item in threading.enumerate()}
            await asyncio.to_thread(self._write_report, metrics, task_lines, frames, threads)
        except Exception:  # noqa: BLE001 - a diagnostic must never break the monitor loop
            logger.exception("Runaway dump failed")
        finally:
            self._writing = False

    @staticmethod
    def _asyncio_task_lines() -> list[str]:
        """Render asyncio task stacks; this must run on the event-loop thread."""
        lines = ["== asyncio tasks =="]
        for task in sorted(asyncio.all_tasks(), key=lambda item: item.get_name()):
            if task.done():
                continue
            coroutine = task.get_coro()
            name = getattr(coroutine, "__qualname__", type(coroutine).__name__)
            lines.append(f"-- {task.get_name()} :: {name}")
            for frame in task.get_stack(limit=_MAX_FRAMES_PER_STACK):
                lines.append("".join(traceback.format_stack(frame, limit=_MAX_FRAMES_PER_STACK)).rstrip())
        return lines

    def _write_report(
        self,
        metrics: _Sample,
        task_lines: list[str],
        frames: dict[int, FrameType],
        threads: dict[int | None, str],
    ) -> None:
        """Render the report and persist it; runs on a worker thread."""
        lines = [
            f"runaway report at {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"cpu_percent={metrics.cpu_percent:.1f}",
            f"thread_count={threading.active_count()}",
            "",
            *task_lines,
            "",
            "== threads (identical stacks aggregated) ==",
        ]
        aggregated: dict[str, list[str]] = {}
        for ident, frame in frames.items():
            stack = "".join(traceback.format_stack(frame, limit=_MAX_FRAMES_PER_STACK)).rstrip()
            aggregated.setdefault(stack, []).append(threads.get(ident, f"unknown thread {ident}"))

        for index, (stack, headers) in enumerate(sorted(aggregated.items(), key=lambda item: -len(item[1]))):
            if index >= _MAX_THREAD_SAMPLES:
                lines.append(f"... {len(aggregated) - _MAX_THREAD_SAMPLES} more distinct stacks omitted")
                break
            lines.append(f"-- {len(headers)} thread(s): {', '.join(headers[:5])}")
            lines.append(stack)

        report = "\n".join(lines)
        if len(report) > _MAX_REPORT_BYTES:
            report = report[:_MAX_REPORT_BYTES] + "\n... report truncated"

        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"runaway-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.txt"
        path.write_text(report, encoding="utf-8")
        logger.warning("Runaway report written to %s", path)
        for stale in sorted(self._log_dir.glob("runaway-*.txt"))[:-_KEEP_REPORTS]:
            stale.unlink(missing_ok=True)
