"""Report the tasks a running event loop is still waiting on, for a test that can hang after its work is done.

[INPUT]
- asyncio (POS: every running loop in the process is found through the garbage collector)

[OUTPUT]
- pending_task_report: text with the stack of every unfinished task of every running loop
- report_pending_tasks_after: context manager that writes that report to the real stderr when its block outlives a deadline

[POS]
Server pytest-only diagnostic. A thread-method pytest timeout ends a hung run with thread stacks, and those show an idle loop
(``select``) rather than the await no task ever leaves; the report written a little before that timeout names it.
"""

from __future__ import annotations

import asyncio
import gc
import io
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

_STACK_LIMIT = 14


def pending_task_report() -> str:
    """The unfinished tasks of every running loop, each with the await it is parked on."""
    lines: list[str] = []
    for candidate in gc.get_objects():
        if not isinstance(candidate, asyncio.AbstractEventLoop) or not candidate.is_running():
            continue
        tasks = [task for task in asyncio.all_tasks(candidate) if not task.done()]
        lines.append(f"== running loop {id(candidate):#x}: {len(tasks)} unfinished task(s)")
        for task in tasks:
            stack = io.StringIO()
            task.print_stack(limit=_STACK_LIMIT, file=stack)
            lines.append(f"-- {task.get_name()} {task.get_coro()!r}\n{stack.getvalue()}")
    return "\n".join(lines) if lines else "== no running event loop"


@contextmanager
def report_pending_tasks_after(seconds: float) -> Iterator[None]:
    """Write ``pending_task_report()`` to the real stderr if the block is still running after *seconds*."""

    def _write() -> None:
        print(pending_task_report(), file=sys.__stderr__, flush=True)

    timer = threading.Timer(seconds, _write)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
