"""OneBot reverse WebSocket: the channel talks to a real websockets client, not to mocks."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
import websockets
from websockets.exceptions import ConnectionClosed

from app.channels.providers.onebot.channel import OneBotChannel
from app.channels.types import OutboundMessage

_TOKEN = "secret-token"


@pytest_asyncio.fixture
async def channel() -> AsyncIterator[OneBotChannel]:
    ch = OneBotChannel(host="127.0.0.1", port=0, access_token=_TOKEN)
    await ch.start()
    yield ch
    await ch.stop()


def _url(ch: OneBotChannel) -> str:
    assert ch._server is not None
    return f"ws://127.0.0.1:{ch._server.sockets[0].getsockname()[1]}"


async def _until(predicate: object) -> None:
    for _ in range(100):
        if callable(predicate) and predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached in time")


@pytest.mark.asyncio
async def test_a_client_with_the_token_is_served_and_gets_the_text(channel: OneBotChannel) -> None:
    async with websockets.connect(_url(channel), additional_headers={"Authorization": f"Bearer {_TOKEN}"}) as client:
        await _until(lambda: channel._active_ws is not None)

        msg = OutboundMessage(channel="onebot", recipient_id="42", content="hello", user_id="u1")
        sending = asyncio.create_task(channel.send(msg))

        request = json.loads(await asyncio.wait_for(client.recv(), timeout=2))
        assert request["action"] == "send_private_msg"
        assert request["params"]["user_id"] == 42
        await client.send(json.dumps({"echo": request["echo"], "status": "ok", "data": {"message_id": 7}}))

        assert await asyncio.wait_for(sending, timeout=2) == "7"


@pytest.mark.asyncio
async def test_a_client_without_the_token_is_closed_and_never_becomes_the_active_one(
    channel: OneBotChannel,
) -> None:
    async with websockets.connect(_url(channel)) as client:
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(client.recv(), timeout=2)
        assert client.close_code == 1008
    assert channel._active_ws is None
