"""Report the tasks a running event loop is still waiting on, for a test that can hang after its work is done.

[INPUT]
- asyncio (POS: every running loop in the process is found through the garbage collector)

[OUTPUT]
- pending_task_report: text with the await chain of every unfinished task of every running loop, from the task's own coroutine down to the
  future it waits on
- report_pending_tasks_after: context manager that writes that report to the real stderr when its block outlives a deadline

[POS]
Server pytest-only diagnostic. A thread-method pytest timeout ends a hung run with thread stacks, and those show an idle loop
(``select``) rather than the await no task ever leaves; the report written a little before that timeout names it.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import sys
import threading
import types
from collections.abc import Iterator
from contextlib import contextmanager

_CHAIN_LIMIT = 40


def _frame_line(frame: types.FrameType) -> str:
    code = frame.f_code
    return f"  {code.co_filename}:{frame.f_lineno} in {code.co_name}"


def _parked_on(awaiting: object) -> object:
    """What a coroutine that is awaiting ``awaiting`` is really parked on.

    ``await future`` waits on a ``FutureIter`` and ``await anext(generator)`` on a step object; each only refers to the future or the
    generator that matters, which is found through its referents.
    """
    if inspect.iscoroutine(awaiting) or inspect.isasyncgen(awaiting) or isinstance(awaiting, asyncio.Future):
        return awaiting
    for referent in gc.get_referents(awaiting):
        if inspect.iscoroutine(referent) or inspect.isasyncgen(referent) or isinstance(referent, asyncio.Future):
            return referent
    return awaiting


def _await_chain(root: object) -> list[str]:
    """Where a coroutine is parked: one line per frame of the coroutines, async generators and awaited tasks below it, then the future."""
    lines: list[str] = []
    current: object | None = root
    while current is not None and len(lines) < _CHAIN_LIMIT:
        frame = getattr(current, "cr_frame", None) or getattr(current, "ag_frame", None)
        if frame is not None:
            lines.append(_frame_line(frame))
        awaiting = getattr(current, "cr_await", None) or getattr(current, "ag_await", None)
        if awaiting is None:
            break
        target = _parked_on(awaiting)
        if isinstance(target, asyncio.Task):
            lines.append(f"  waits on task {target.get_name()}:")
            current = target.get_coro()
        elif inspect.iscoroutine(target) or inspect.isasyncgen(target):
            current = target
        else:
            lines.append(f"  waits on {target!r}")
            break
    return lines


def pending_task_report() -> str:
    """The unfinished tasks of every running loop, each with the chain of awaits it is parked on."""
    lines: list[str] = []
    for candidate in gc.get_objects():
        if not isinstance(candidate, asyncio.AbstractEventLoop) or not candidate.is_running():
            continue
        tasks = [task for task in asyncio.all_tasks(candidate) if not task.done()]
        lines.append(f"== running loop {id(candidate):#x}: {len(tasks)} unfinished task(s)")
        for task in tasks:
            lines.append(f"-- {task.get_name()} cancelling={task.cancelling()} {task.get_coro()!r}")
            lines.extend(_await_chain(task.get_coro()))
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
