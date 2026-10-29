"""Tests for the HTTP route that ``TelegramWebhookMixin.register_routes`` binds.

The route is driven end to end: a real Starlette request, adapted exactly as the FastAPI registrar does, goes
through the real security middleware and the registered handler; only the downstream update processing is replaced.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.channels.implementations.fastapi.adapters import FastAPIRequestAdapter
from app.channels.protocols.route_registrar import GenericRequest, GenericResponse, HttpMethod
from app.channels.providers.telegram import TelegramChannel
from app.channels.testing.route_testing import MockRouteRegistrar
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN


def _request(body: bytes, *, secret: str | None) -> GenericRequest:
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if secret is not None:
        headers.append((b"x-telegram-bot-api-secret-token", secret.encode()))

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


def _bound() -> tuple[TelegramChannel, AsyncMock, MockRouteRegistrar]:
    channel = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    dispatch = AsyncMock()
    channel.handle_webhook_update = dispatch  # type: ignore[method-assign]
    registrar = MockRouteRegistrar()
    channel.register_routes(registrar)
    return channel, dispatch, registrar


async def _post(registrar: MockRouteRegistrar, request: GenericRequest) -> GenericResponse:
    return await registrar.registered_routes[0].handler(request)


def test_registers_a_single_unauthenticated_post_webhook_route() -> None:
    _, _, registrar = _bound()

    assert [(route.method, route.path) for route in registrar.registered_routes] == [(HttpMethod.POST, "webhook")]
    assert registrar.registered_routes[0].metadata.requires_auth is False


@pytest.mark.asyncio
async def test_valid_update_is_acknowledged_and_dispatched() -> None:
    channel, dispatch, registrar = _bound()
    update = {"update_id": 7, "message": {"message_id": 1, "text": "hi"}}

    response = await _post(registrar, _request(json.dumps(update).encode(), secret=channel.webhook_secret))

    assert (response.status_code, response.headers, response.body) == (200, {}, b'{"ok": true}')
    dispatch.assert_awaited_once_with(update)


@pytest.mark.asyncio
async def test_wrong_secret_is_rejected_without_dispatch() -> None:
    _, dispatch, registrar = _bound()

    response = await _post(registrar, _request(b'{"update_id": 1}', secret="not-the-secret"))

    assert response.status_code == 403
    assert json.loads(response.body)["type"].endswith("/signature-invalid")
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_json_is_rejected_without_dispatch() -> None:
    channel, dispatch, registrar = _bound()

    response = await _post(registrar, _request(b"{not json", secret=channel.webhook_secret))

    assert response.status_code >= 400
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_processing_failure_is_reported_as_internal_error() -> None:
    channel, dispatch, registrar = _bound()
    dispatch.side_effect = RuntimeError("boom")

    response = await _post(registrar, _request(b'{"update_id": 1}', secret=channel.webhook_secret))

    assert response.status_code == 500
    assert json.loads(response.body) == {"ok": False, "error": "Internal error"}


def test_an_object_that_is_not_a_route_registrar_is_ignored() -> None:
    not_a_registrar = MagicMock(spec=[])

    TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN).register_routes(not_a_registrar)

    assert not_a_registrar.mock_calls == []
