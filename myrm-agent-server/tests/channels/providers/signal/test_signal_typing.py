"""Signal typing indicators follow the rules of signal-cli-rest-api, for direct chats and groups.

The fake wrapper enforces what bbernhard/signal-cli-rest-api does (``src/api/api.go`` ``SendStartTyping`` /
``SendStopTyping``): ``PUT`` and ``DELETE /v1/typing-indicator/{number}`` both bind a JSON body with a ``recipient``, so a
``DELETE`` without a body is a 400, and the recipient is a number, a UUID or ``group.`` + base64 of the group's bare id
(``src/client/client.go`` ``getRecipientType``).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.channels.providers.signal import SignalChannel

from .test_signal_reactions import GROUP_ID, GROUP_RECIPIENT, NUMBER, USER, _valid_recipient


class _FakeWrapper:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.refused: list[tuple[str, str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != f"/v1/typing-indicator/{NUMBER}" or request.method not in {"PUT", "DELETE"}:
            return httpx.Response(404)
        try:
            body = json.loads(request.content)
        except ValueError:
            self.refused.append((request.method, "no JSON body"))
            return httpx.Response(400, json={"error": "Couldn't process request - invalid request"})
        if not _valid_recipient(body.get("recipient")):
            self.refused.append((request.method, f"recipient {body.get('recipient')!r}"))
            return httpx.Response(400, json={"error": "invalid recipient"})
        self.calls.append((request.method, body))
        return httpx.Response(204)


def _channel() -> tuple[SignalChannel, _FakeWrapper]:
    wrapper = _FakeWrapper()
    ch = SignalChannel(api_url="http://signal:8080", phone_number=NUMBER)
    ch._api._http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper.handle))
    return ch, wrapper


@pytest.mark.asyncio
async def test_typing_starts_and_stops_naming_a_direct_chat() -> None:
    ch, wrapper = _channel()

    await ch.start_typing(USER)
    await ch.stop_typing(USER)

    assert wrapper.calls == [("PUT", {"recipient": USER}), ("DELETE", {"recipient": USER})]
    assert wrapper.refused == []


@pytest.mark.asyncio
async def test_typing_starts_and_stops_naming_a_group_in_the_form_the_wrapper_accepts() -> None:
    ch, wrapper = _channel()

    await ch.start_typing(GROUP_ID)
    await ch.stop_typing(GROUP_ID)

    assert wrapper.calls == [("PUT", {"recipient": GROUP_RECIPIENT}), ("DELETE", {"recipient": GROUP_RECIPIENT})]
    assert wrapper.refused == []


@pytest.mark.asyncio
async def test_a_refused_typing_request_is_raised_by_the_client_and_never_reaches_the_chat() -> None:
    """The client reports the refusal instead of dropping the status; the channel only logs it at debug level."""
    ch = SignalChannel(api_url="http://signal:8080", phone_number=NUMBER)
    refuse = httpx.MockTransport(lambda _request: httpx.Response(400, json={"error": "refused"}))
    ch._api._http = httpx.AsyncClient(transport=refuse)

    with pytest.raises(httpx.HTTPStatusError):
        await ch._api.start_typing(USER)
    await ch.start_typing(USER)
    await ch.stop_typing(USER)
