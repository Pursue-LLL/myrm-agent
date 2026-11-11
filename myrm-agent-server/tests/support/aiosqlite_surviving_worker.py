"""Plugin: an aiosqlite connection keeps answering after the event loop that last awaited it has closed.

aiosqlite hands every result back through ``future.get_loop().call_soon_threadsafe``. The suite opens connections in one
test's loop and keeps them in process-wide caches and shared engines that a later test uses from another loop. A worker
thread that finishes a query after the loop that asked for it has closed raises there, and the exception ends the thread
with the rest of its queue unanswered: every later request on that connection waits forever, ``close()`` included, and a
single cancellation does not interrupt a ``close()`` that waits for the stopped worker. A test teardown that touches such
a connection (the ``client`` fixture of the agent API tests cancelling a turn, an engine disposal, a cache shutdown) holds
the session until the CI time limit.

The worker installed here drops an answer nobody can read and goes on serving the queue. ``library_aiosqlite_worker``
restores the library's own worker for a test that needs a connection to die that way.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from queue import SimpleQueue

import aiosqlite.core as aiosqlite_core
import pytest

_Request = tuple[asyncio.Future[object] | None, Callable[[], object]]

LIBRARY_WORKER = aiosqlite_core._connection_worker_thread


def _answer(future: asyncio.Future[object] | None, settle: Callable[..., None], value: object) -> None:
    if future is None:
        return
    try:
        future.get_loop().call_soon_threadsafe(settle, future, value)
    except RuntimeError:
        # The loop that asked is closed, so no one is left to read the answer.
        return


def surviving_worker(tx: SimpleQueue[_Request]) -> None:
    while True:
        future, function = tx.get()
        try:
            result = function()
            _answer(future, aiosqlite_core.set_result, result)
            if result is aiosqlite_core._STOP_RUNNING_SENTINEL:
                break
        except BaseException as error:  # noqa: BLE001 - one failed request must not end the thread
            _answer(future, aiosqlite_core.set_exception, error)


def pytest_configure(config: pytest.Config) -> None:
    aiosqlite_core._connection_worker_thread = surviving_worker
    config.add_cleanup(lambda: setattr(aiosqlite_core, "_connection_worker_thread", LIBRARY_WORKER))


@pytest.fixture
def library_aiosqlite_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connections opened during the test run on aiosqlite's own worker, which ends when its loop closes mid-query."""
    monkeypatch.setattr(aiosqlite_core, "_connection_worker_thread", LIBRARY_WORKER)
