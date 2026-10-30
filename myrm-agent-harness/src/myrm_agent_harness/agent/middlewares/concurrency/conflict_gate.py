"""First-come-first-served gate: shared holders run together, an exclusive holder runs alone.

[INPUT]
- asyncio (POS: futures that park a waiting holder on the running event loop)

[OUTPUT]
- ConflictGate: the admission queue; ``hold(exclusive=...)`` is the async context a holder runs in

[POS]
The mutual-exclusion primitive under ``ToolConflictGateMiddleware``. Admission follows arrival order, so an
exclusive holder that is waiting is never starved by shared holders that arrive after it, and a holder that
stops waiting (cancelled) never keeps the ones behind it out.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

_Turn = tuple[bool, "asyncio.Future[None]"]


class ConflictGate:
    """Admits shared holders together and an exclusive holder alone, in arrival order."""

    def __init__(self) -> None:
        self._shared_holders = 0
        self._exclusive_held = False
        self._waiting: deque[_Turn] = deque()

    @asynccontextmanager
    async def hold(self, *, exclusive: bool) -> AsyncIterator[None]:
        """Run the body once admitted; the hold ends however the body ends."""
        await self._enter(exclusive)
        try:
            yield
        finally:
            self._leave(exclusive)

    def _admits(self, exclusive: bool) -> bool:
        if self._exclusive_held:
            return False
        return self._shared_holders == 0 if exclusive else True

    def _take(self, exclusive: bool) -> None:
        if exclusive:
            self._exclusive_held = True
        else:
            self._shared_holders += 1

    def _leave(self, exclusive: bool) -> None:
        if exclusive:
            self._exclusive_held = False
        else:
            self._shared_holders -= 1
        self._admit_waiting()

    def _admit_waiting(self) -> None:
        """Admit waiters from the front for as long as the head of the line can run."""
        while self._waiting:
            exclusive, admitted = self._waiting[0]
            if admitted.done():
                # Cancelled before its task noticed: there is no one to admit, and that task finds itself gone.
                self._waiting.popleft()
                continue
            if not self._admits(exclusive):
                return
            self._waiting.popleft()
            self._take(exclusive)
            admitted.set_result(None)

    async def _enter(self, exclusive: bool) -> None:
        if not self._waiting and self._admits(exclusive):
            self._take(exclusive)
            return
        turn: _Turn = (exclusive, asyncio.get_running_loop().create_future())
        self._waiting.append(turn)
        try:
            await turn[1]
        except BaseException:
            if turn[1].done() and not turn[1].cancelled():
                # Admitted in the same loop iteration the cancellation arrived in: the hold is ours to give back.
                self._leave(exclusive)
            else:
                with suppress(ValueError):
                    self._waiting.remove(turn)
                self._admit_waiting()
            raise
