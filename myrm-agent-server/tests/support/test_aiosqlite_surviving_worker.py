"""A connection keeps answering after the loop that asked its last query has closed, and closes however many tasks close it."""

from __future__ import annotations

import asyncio
import time

import aiosqlite
import pytest

_NAP_SECONDS = 0.3
_ANSWER_BOUND_SECONDS = 10.0
_NO_ANSWER_BOUND_SECONDS = 1.0


def _connection_whose_loop_closed_mid_query() -> aiosqlite.Connection:
    """Open a connection, then close its event loop while the worker thread is still inside a query."""

    async def open_and_leave_a_query_running() -> aiosqlite.Connection:
        connection = await aiosqlite.connect(":memory:")
        await connection.create_function("nap", 1, lambda seconds: time.sleep(seconds) or 1)
        asyncio.ensure_future(connection.execute(f"SELECT nap({_NAP_SECONDS})"))
        await asyncio.sleep(0.05)
        return connection

    return asyncio.run(open_and_leave_a_query_running())


async def _select_one(connection: aiosqlite.Connection, bound: float) -> tuple[object, ...]:
    cursor = await asyncio.wait_for(connection.execute("SELECT 1"), bound)
    row = await cursor.fetchone()
    return tuple(row) if row is not None else ()


@pytest.mark.timeout(60)
def test_a_connection_answers_from_another_loop_after_its_own_loop_closed_mid_query() -> None:
    connection = _connection_whose_loop_closed_mid_query()

    async def ask_and_close() -> tuple[object, ...]:
        row = await _select_one(connection, _ANSWER_BOUND_SECONDS)
        await asyncio.wait_for(connection.close(), _ANSWER_BOUND_SECONDS)
        return row

    assert asyncio.run(ask_and_close()) == (1,)


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("library_aiosqlite_worker")
def test_the_library_worker_stops_answering_once_its_loop_closed_mid_query() -> None:
    """The premise of the plugin: without it the connection above would never answer again."""
    connection = _connection_whose_loop_closed_mid_query()

    with pytest.raises(TimeoutError):
        asyncio.run(_select_one(connection, _NO_ANSWER_BOUND_SECONDS))


async def _closers_left_waiting(bound: float) -> int:
    """Close one connection from two tasks at once and count the closers that have not returned after ``bound``."""
    connection = await aiosqlite.connect(":memory:")
    closers = {asyncio.ensure_future(connection.close()), asyncio.ensure_future(connection.close())}
    _, waiting = await asyncio.wait(closers, timeout=bound)
    for closer in waiting:
        closer.cancel()
    return len(waiting)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_two_tasks_closing_one_connection_at_once_both_return() -> None:
    assert await _closers_left_waiting(_ANSWER_BOUND_SECONDS) == 0


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("library_aiosqlite_stop")
async def test_the_library_leaves_one_of_two_closers_waiting_forever() -> None:
    """The premise of the guard: without it the second closer waits for a stop that no worker thread serves."""
    assert await _closers_left_waiting(_NO_ANSWER_BOUND_SECONDS) == 1
