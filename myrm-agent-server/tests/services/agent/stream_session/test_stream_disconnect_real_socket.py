"""Direct-SSE disconnect tolerance over a real uvicorn socket.

The unit tests in ``test_stream_disconnect.py`` replace ``Request.is_disconnected`` or feed it a ``receive`` written for the test. uvicorn's own
``receive`` suspends and wakes differently, and a real client leaving is a TCP close, so these two behaviours are checked with both of them real:
the turn is cancelled once a client that really left stays away past the grace period, and a turn that ends while the monitor polls does not
wait for the client.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
import uvicorn
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

from app.services.agent.stream_session import stream_disconnect
from app.services.agent.stream_session.stream_disconnect import watch_client_disconnect
from app.services.agent.stream_session.stream_session_types import ACTIVITY_STALE_SECONDS, AgentStreamSession

Turn = Callable[[AgentStreamSession], Coroutine[None, None, None]]

_STARTUP_TIMEOUT_SECONDS = 5.0


class _Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield  # the test runner owns the process's signal handlers


def _session(request: Request) -> AgentStreamSession:
    """Fake session for a client that is really connected: the grace clock is monotonic and cancellation also needs stale activity."""
    return cast(
        AgentStreamSession,
        SimpleNamespace(
            request=SimpleNamespace(multiplexed=False),
            http_request=request,
            collector=SimpleNamespace(has_subscribers=False),
            params=SimpleNamespace(message_id="msg-1"),
            cancel_token=CancellationToken(request_id="msg-1"),
            is_long_running_task=False,
            disconnect_monotonic=None,
            disconnect_time=None,
            last_activity_monotonic=time.monotonic() - ACTIVITY_STALE_SECONDS - 1,
        ),
    )


class _TurnApp:
    """An endpoint whose turn runs in its own task, decoupled from the response as the server's buffered turns are."""

    def __init__(self, turn: Turn) -> None:
        self.sessions: list[AgentStreamSession] = []
        self.turns: list[asyncio.Task[None]] = []
        self._turn = turn
        self.asgi = Starlette(routes=[Route("/turn", self._handle)])

    async def _handle(self, request: Request) -> StreamingResponse:
        session = _session(request)
        self.sessions.append(session)
        turn = asyncio.create_task(self._turn(session))
        self.turns.append(turn)

        async def stream() -> AsyncIterator[bytes]:
            yield b"data: started\n\n"
            await asyncio.wait({turn})
            yield b"data: done\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")


@contextlib.asynccontextmanager
async def _serving(app: _TurnApp) -> AsyncIterator[int]:
    server = _Server(uvicorn.Config(app.asgi, host="127.0.0.1", port=0, log_level="error", timeout_graceful_shutdown=1))
    serving = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(_STARTUP_TIMEOUT_SECONDS):
            while not server.started:
                if serving.done():
                    serving.result()
                await asyncio.sleep(0.005)
        yield server.servers[0].sockets[0].getsockname()[1]
    finally:
        for turn in app.turns:
            turn.cancel()
        server.should_exit = True
        await serving


@pytest.fixture
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(stream_disconnect, "_CHECK_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(stream_disconnect, "GRACE_PERIOD_SECONDS", 0.05)
    yield


@pytest.mark.asyncio
@pytest.mark.usefixtures("fast_polling")
async def test_a_client_that_really_left_cancels_the_turn_after_the_grace_period() -> None:
    async def turn(session: AgentStreamSession) -> None:
        async with watch_client_disconnect(session):
            while not session.cancel_token.is_cancelled:
                await asyncio.sleep(0.005)

    app = _TurnApp(turn)
    async with _serving(app) as port:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(b"GET /turn HTTP/1.1\r\nHost: test\r\n\r\n")
            await writer.drain()
            await asyncio.wait_for(reader.readuntil(b"data: started\n\n"), timeout=2)
            await asyncio.sleep(0.2)  # several polls and the grace period: a connected client is never cancelled
            assert not app.sessions[0].cancel_token.is_cancelled
        finally:
            writer.close()

        await asyncio.wait_for(asyncio.shield(app.turns[0]), timeout=3)

    assert app.sessions[0].cancel_token.cancel_reason == CancelReason.DISCONNECT


@pytest.mark.asyncio
@pytest.mark.usefixtures("fast_polling")
async def test_turns_that_end_while_the_monitor_polls_never_wait_for_their_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no pause between polls the end of a turn often lands in the loop step where the poll's cancel scope delivers its cancellation;
    the old monitor then kept polling and the turn's exit waited for a client that stayed connected."""
    monkeypatch.setattr(stream_disconnect, "_CHECK_INTERVAL_SECONDS", 0.0)
    requests = 60

    async def turn(session: AgentStreamSession) -> None:
        async with watch_client_disconnect(session):
            await asyncio.sleep(len(app.sessions) % 20 * 0.0015)

    app = _TurnApp(turn)
    async with _serving(app) as port, httpx.AsyncClient(timeout=10) as client:
        gate = asyncio.Semaphore(20)

        async def one_turn() -> bool:
            async with gate:
                try:
                    response = await asyncio.wait_for(client.get(f"http://127.0.0.1:{port}/turn"), timeout=2)
                except TimeoutError:
                    return False
                return b"data: done" in response.content

        finished = await asyncio.gather(*(one_turn() for _ in range(requests)))

    assert finished.count(False) == 0, f"{finished.count(False)} of {requests} turns did not end"
