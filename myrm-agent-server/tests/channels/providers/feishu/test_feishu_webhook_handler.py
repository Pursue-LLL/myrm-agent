"""The HTTP route ``FeishuChannel.register_routes`` binds answers every callback with a status and a body.

The route is driven end to end: a real Starlette request, adapted exactly as the FastAPI registrar does, goes through
the real security middleware and the registered handler; only the event processing is replaced.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.channels.implementations.fastapi.adapters import FastAPIRequestAdapter
from app.channels.protocols.route_registrar import GenericRequest, GenericResponse
from app.channels.providers.feishu import FeishuChannel
from app.channels.testing.route_testing import MockRouteRegistrar

_APP_ID = "test_app_id"


def _request(body: bytes) -> GenericRequest:
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhook",
        "query_string": b"",
        "headers": headers,
        "client": ("203.0.113.7", 40000),
    }
    return FastAPIRequestAdapter().adapt(Request(scope, receive))


def _bound(event_result: dict[str, object] | None = None) -> tuple[AsyncMock, MockRouteRegistrar]:
    channel = FeishuChannel(app_id=_APP_ID, app_secret="test_app_secret")
    process = AsyncMock(return_value=event_result)
    channel.handle_webhook_event = process  # type: ignore[method-assign]
    registrar = MockRouteRegistrar()
    channel.register_routes(registrar)
    return process, registrar


async def _post(registrar: MockRouteRegistrar, body: bytes) -> GenericResponse:
    return await registrar.registered_routes[0].handler(_request(body))


@pytest.mark.asyncio
async def test_an_event_without_a_reply_is_acknowledged() -> None:
    process, registrar = _bound()
    event = {"header": {"app_id": _APP_ID}, "event": {}}

    response = await _post(registrar, json.dumps(event).encode())

    assert (response.status_code, response.headers, response.body) == (200, {}, b'{"ok": true}')
    process.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_the_result_of_event_processing_is_the_response_body() -> None:
    _, registrar = _bound({"challenge": "token"})

    response = await _post(registrar, b'{"challenge": "token"}')

    assert (response.status_code, response.headers) == (200, {})
    assert json.loads(response.body) == {"challenge": "token"}


@pytest.mark.asyncio
async def test_an_event_for_another_app_is_rejected_without_processing() -> None:
    process, registrar = _bound()

    response = await _post(registrar, b'{"header": {"app_id": "someone_else"}}')

    assert response.status_code == 403
    assert json.loads(response.body)["type"].endswith("/app-id-mismatch")
    process.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_body_that_is_not_json_is_rejected_without_processing() -> None:
    process, registrar = _bound()

    response = await _post(registrar, b"not json")

    assert response.status_code == 400
    process.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failure_while_processing_answers_500_without_the_reason() -> None:
    process, registrar = _bound()
    process.side_effect = RuntimeError("secret internal detail")

    response = await _post(registrar, b'{"header": {"app_id": "test_app_id"}}')

    assert (response.status_code, response.headers) == (500, {})
    assert json.loads(response.body) == {"ok": False, "error": "Internal error"}
