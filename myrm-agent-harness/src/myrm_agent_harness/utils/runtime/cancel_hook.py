"""Run a callback the moment a request's token is cancelled.

A cancelled token is only a flag; a consumer blocked on a slow stream never looks at it until the next event.
``on_token_cancelled`` closes that gap for work that can be stopped from outside (killing a delegated process):
a watcher fires the callback within one poll interval while the guarded block keeps awaiting its stream.

[INPUT]
- .cancellation::CancellationToken (POS: Cancellation token mechanism. Provides request-level cancellation state management)

[OUTPUT]
- on_token_cancelled: async context manager that calls ``callback`` once if the token is cancelled inside the block
- DeadlineCut / cut_deadline_on_cancel: end an ``asyncio.timeout`` scope as soon as the token is cancelled and record that the token, not the clock, ended it

[POS]
Cancellation bridge for streams that must be stopped from outside; the counterpart of ``run_until_cancelled``, which
aborts an awaited operation instead. ``cut_deadline_on_cancel`` suits work that already unwinds through its own
timeout handling (kill the process, keep the partial output): the cancel takes the same exit as a timeout.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from .cancellation import CancellationToken

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 0.25


async def _call_when_cancelled(token: CancellationToken, callback: Callable[[], Awaitable[None]]) -> None:
    while not token.is_cancelled:
        await asyncio.sleep(_POLL_INTERVAL_S)
    try:
        await callback()
    except Exception:
        logger.warning("cancel_hook_failed request_id=%s", token.request_id, exc_info=True)


@asynccontextmanager
async def on_token_cancelled(
    token: CancellationToken | None,
    callback: Callable[[], Awaitable[None]],
) -> AsyncIterator[None]:
    """Call ``callback`` (once) as soon as ``token`` is cancelled while the block runs; a ``None`` token never fires."""
    if token is None:
        yield
        return
    watcher = asyncio.create_task(_call_when_cancelled(token, callback))
    try:
        yield
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher


@dataclass
class DeadlineCut:
    """Whether a timeout scope was ended early because the request was cancelled (and not because time ran out)."""

    by_cancel: bool = False


@asynccontextmanager
async def cut_deadline_on_cancel(
    token: CancellationToken | None,
    deadline: asyncio.Timeout,
    cut: DeadlineCut,
) -> AsyncIterator[None]:
    """End ``deadline`` now when ``token`` is cancelled inside the block, and record that in ``cut``.

    The scope then fails with ``TimeoutError`` exactly as an expired deadline does; ``cut.by_cancel`` tells the
    handler which of the two happened. A ``None`` token never cuts.
    """

    async def cut_now() -> None:
        cut.by_cancel = True
        deadline.reschedule(asyncio.get_running_loop().time())

    async with on_token_cancelled(token, cut_now):
        yield
