"""iMessage follows the Private API state BlueBubbles reports, not the state it saw at start.

BlueBubbles refuses a Tapback, a typing indicator, a read receipt or a quoted reply unless ``private_api`` is on
and the helper is connected (bluebubbles-server ``checkPrivateApiStatus``), and both can change after start: the
helper may connect late or drop. The fake server answers ``/server/info`` from flags the test flips and records
what it is asked to do, so every feature is checked against the server's own view.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.channels.providers.imessage import IMessageChannel
from app.channels.types import OutboundMessage

_CHAT = "iMessage;-;+15551234567"
_THUMBS_UP = "\U0001f44d"


class _FakeBlueBubbles:
    """``/server/info`` reports the flags; the Private API endpoints are recorded as (name, body)."""

    def __init__(self, *, private_api: bool = True, helper: bool = True) -> None:
        self.private_api = private_api
        self.helper = helper
        self.info_body: bytes | None = None
        self.info_status = 200
        self.calls: list[tuple[str, dict[str, object]]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/server/info":
            if self.info_body is not None:
                return httpx.Response(self.info_status, content=self.info_body)
            data = {"private_api": self.private_api, "helper_connected": self.helper}
            return httpx.Response(self.info_status, json={"data": data})
        body = json.loads(request.content) if request.content else {}
        name = "tapback" if path.endswith("/message/react") else path.rsplit("/", 1)[-1]
        self.calls.append((name, body))
        return httpx.Response(200, json={"data": {"guid": "g-1"}})

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


def _channel(server: _FakeBlueBubbles) -> IMessageChannel:
    ch = IMessageChannel(api_url="http://localhost:1234", password="pw")
    ch._http = httpx.AsyncClient(transport=httpx.MockTransport(server.handle))
    return ch


async def _running(server: _FakeBlueBubbles) -> IMessageChannel:
    ch = _channel(server)
    await ch.start()
    return ch


def _quoted() -> OutboundMessage:
    return OutboundMessage(channel="imessage", recipient_id=_CHAT, content="hi", user_id="U", reply_to_id="orig-guid")


async def _every_feature(ch: IMessageChannel) -> None:
    await ch.start_typing(_CHAT)
    await ch.stop_typing(_CHAT)
    await ch._mark_read(_CHAT)
    await ch.react_to_message(_CHAT, "msg-1", _THUMBS_UP)
    await ch.send(_quoted())


class TestFlagsFollowServerInfo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("private_api", "helper"), [(True, True), (True, False), (False, False), (False, True)])
    async def test_start_takes_the_flags_from_the_server(self, private_api: bool, helper: bool) -> None:
        ch = await _running(_FakeBlueBubbles(private_api=private_api, helper=helper))
        assert (ch.private_api_available, ch.helper_connected) == (private_api, helper)

    @pytest.mark.asyncio
    async def test_a_helper_that_connects_after_start_is_picked_up_by_the_next_health_check(self) -> None:
        server = _FakeBlueBubbles(helper=False)
        ch = await _running(server)

        await ch.send(_quoted())
        assert server.calls[-1][1].get("method") is None

        server.helper = True
        assert await ch.health_check() is True
        await ch.send(_quoted())

        assert ch.helper_connected is True
        assert server.calls[-1][1]["method"] == "private-api"
        assert server.calls[-1][1]["selectedMessageGuid"] == "orig-guid"

    @pytest.mark.asyncio
    async def test_a_helper_that_drops_is_picked_up_by_the_next_health_check(self) -> None:
        server = _FakeBlueBubbles()
        ch = await _running(server)

        server.helper = False
        await ch.health_check()
        await _every_feature(ch)

        assert server.names() == ["text"]
        assert server.calls[0][1].get("method") is None

    @pytest.mark.asyncio
    async def test_a_server_info_that_cannot_be_read_keeps_the_last_state(self) -> None:
        server = _FakeBlueBubbles()
        ch = await _running(server)

        server.info_body = b"<html>proxy page</html>"
        assert await ch.health_check() is True

        assert (ch.private_api_available, ch.helper_connected) == (True, True)

    @pytest.mark.asyncio
    async def test_a_failed_health_check_keeps_the_last_state(self) -> None:
        server = _FakeBlueBubbles()
        ch = await _running(server)

        server.private_api, server.info_status = False, 500
        assert await ch.health_check() is False

        assert (ch.private_api_available, ch.helper_connected) == (True, True)


class TestEveryPrivateApiFeatureUsesTheSameState:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("private_api", "helper"), [(False, False), (True, False), (False, True)])
    async def test_nothing_asks_the_server_for_a_private_api_feature_while_it_is_unavailable(
        self, private_api: bool, helper: bool
    ) -> None:
        server = _FakeBlueBubbles(private_api=private_api, helper=helper)
        ch = await _running(server)

        await _every_feature(ch)

        assert server.names() == ["text"]
        assert server.calls[0][1].get("method") is None

    @pytest.mark.asyncio
    async def test_every_private_api_feature_is_used_once_the_server_reports_it_ready(self) -> None:
        server = _FakeBlueBubbles(private_api=False, helper=False)
        ch = await _running(server)

        server.private_api = server.helper = True
        await ch.health_check()
        await _every_feature(ch)

        assert server.names() == ["typing", "typing", "read", "tapback", "text"]
        assert server.calls[-1][1]["method"] == "private-api"


class TestSkippedTapbackRemoval:
    @pytest.mark.asyncio
    async def test_a_removal_skipped_while_unavailable_is_still_possible_once_the_server_is_ready_again(self) -> None:
        server = _FakeBlueBubbles()
        ch = await _running(server)
        await ch.react_to_message(_CHAT, "msg-1", _THUMBS_UP)

        server.helper = False
        await ch.health_check()
        await ch.react_to_message(_CHAT, "msg-1", "")
        assert server.names() == ["tapback"]

        server.helper = True
        await ch.health_check()
        await ch.react_to_message(_CHAT, "msg-1", "")

        assert [body["reaction"] for name, body in server.calls if name == "tapback"] == ["like", "-like"]
