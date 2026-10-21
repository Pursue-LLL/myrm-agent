"""Failure observation for long-lived background tasks.

An `asyncio.Task` whose exception is never retrieved keeps it silently: nothing is logged,
and a task held alive by a module global never even triggers asyncio's "exception was never
retrieved" report — that report only fires when a task is garbage-collected with the exception
still unread. A scheduler that crashes during startup therefore leaves the process looking
healthy while its periodic jobs are dead.

[INPUT]
- (none)

[OUTPUT]
- spawn_observed_task: start a process-lifetime task whose failure is logged, not dropped

[POS]
为长期存活的 asyncio 后台任务提供统一的「启动 + 失败观测」。与 `resource_monitor` 同属
「必须发生的后台工作」，失败只出现在这条日志里，所以启动处统一走本入口，避免逐个调用点
漏接观测回调。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from functools import partial

logger = logging.getLogger(__name__)


def spawn_observed_task(coroutine: Coroutine[object, object, None], *, name: str) -> asyncio.Task[None]:
    """Start a long-lived task and observe its outcome so a crash cannot go unlogged.

    ``name`` doubles as the asyncio task name, so a stuck or dead scheduler is identifiable in
    faulthandler dumps and ``asyncio.all_tasks()`` output, not just in the failure log.
    """
    task = asyncio.create_task(coroutine, name=name)
    task.add_done_callback(partial(_log_task_failure, name=name))
    return task


def _log_task_failure(task: asyncio.Task[object], *, name: str) -> None:
    """Log a finished background task's exception; cancellation is the normal shutdown path."""
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except Exception as err:
        # A done callback must never raise; surface an unreadable outcome instead of losing it.
        logger.warning("[%s] background task outcome could not be read: %s", name, err)
        return
    if exc is not None:
        logger.error("[%s] background task exited: %s", name, exc, exc_info=exc)


__all__ = ["spawn_observed_task"]
