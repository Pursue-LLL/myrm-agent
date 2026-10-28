"""A stop that cancels a model request closes the connection to the provider.

The model-call cancel wrapper cancels the awaiting task; the provider only stops generating if the HTTP connection
really goes away. A local server accepts the request, says nothing (a long prefill) and reports when the client
disconnects. The request goes through the real chat model factory, for the plain and the streaming call alike.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

import pytest
from langchain_core.messages import HumanMessage

from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationToken,
    CancelReason,
    OperationCancelledError,
    run_until_cancelled,
    set_cancel_token,
)

_STOP_AFTER_REQUEST_S = 0.5
_CLOSED_WITHIN_S = 3.0


@dataclass
class _SilentServer:
    """Accepts one request without answering; records when it arrived and when the client went away."""

    port: int = 0
    request_arrived: asyncio.Event = field(default_factory=asyncio.Event)
    closed_at: float | None = None
    writers: list[asyncio.StreamWriter] = field(default_factory=list)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.writers.append(writer)
        head = await reader.readuntil(b"\r\n\r\n")
        length = next(
            (int(line.split(b":")[1]) for line in head.split(b"\r\n") if line.lower().startswith(b"content-length:")),
            0,
        )
        if length:
            await reader.readexactly(length)
        self.request_arrived.set()
        try:
            while await reader.read(1024):
                pass
        finally:
            self.closed_at = time.monotonic()
            writer.close()


@pytest.fixture
async def silent_server() -> AsyncIterator[_SilentServer]:
    state = _SilentServer()
    server = await asyncio.start_server(state.handle, "127.0.0.1", 0)
    state.port = server.sockets[0].getsockname()[1]
    try:
        yield state
    finally:
        for writer in state.writers:
            writer.close()
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=10)


@pytest.fixture(autouse=True)
def _clean_run_state() -> Iterator[None]:
    yield
    set_cancel_token(None)


@pytest.mark.parametrize("streaming", [False, True], ids=["plain-call", "streaming-call"])
async def test_a_stopped_model_request_closes_the_provider_connection(
    streaming: bool, silent_server: _SilentServer
) -> None:
    model = create_litellm_model(
        "openai/test-model",
        base_url=f"http://127.0.0.1:{silent_server.port}/v1",
        api_key="test-key",
        streaming=streaming,
    )
    token = CancellationToken("stop_closes_connection")
    set_cancel_token(token)
    stopped_at = 0.0

    async def stop_after_the_request_arrived() -> None:
        nonlocal stopped_at
        await asyncio.wait_for(silent_server.request_arrived.wait(), timeout=30)
        await asyncio.sleep(_STOP_AFTER_REQUEST_S)
        stopped_at = time.monotonic()
        token.cancel(CancelReason.USER_CANCELLED)

    stopper = asyncio.create_task(stop_after_the_request_arrived())
    with pytest.raises(OperationCancelledError):
        await asyncio.wait_for(run_until_cancelled(model.ainvoke([HumanMessage(content="hi")])), timeout=60)
    await stopper

    deadline = time.monotonic() + _CLOSED_WITHIN_S
    while silent_server.closed_at is None and time.monotonic() < deadline:
        await asyncio.sleep(0.05)

    assert silent_server.closed_at is not None, "the provider never saw the client go away"
    assert silent_server.closed_at - stopped_at < _CLOSED_WITHIN_S
