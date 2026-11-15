"""A stand-in for ``apscheduler.AsyncScheduler`` that records what is registered instead of running it.

[INPUT]
- apscheduler.triggers.interval::IntervalTrigger (POS: the trigger type the lifecycle schedulers register)

[OUTPUT]
- RecordingScheduler: async-context-manager double; ``registered`` maps a schedule id to its job function and trigger,
  ``started`` is set by ``start_in_background``, ``created_at`` is the moment just before the code under test uses it

[POS]
Server pytest-only helper for tests that boot a real lifecycle scheduler function and inspect its registrations.
APScheduler 4 runs nothing until it is started, so ``started`` also marks the point at which every registration of the
boot is visible; a boot that only registers would leave every job dead.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from apscheduler.triggers.interval import IntervalTrigger


class RecordingScheduler:
    def __init__(self) -> None:
        self.registered: dict[str, tuple[Callable[[], object], IntervalTrigger]] = {}
        self.started = asyncio.Event()
        self.created_at = datetime.now(UTC)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        return None

    async def add_schedule(self, func: Callable[[], object], trigger: IntervalTrigger, *, id: str) -> None:
        self.registered[id] = (func, trigger)

    async def start_in_background(self) -> None:
        self.started.set()
