"""Mocks shared by the Telegram client tests: a client over a mocked HTTP layer and Bot API response builders."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx

from app.channels.providers.telegram.api import TelegramClient


def mock_client() -> tuple[TelegramClient, AsyncMock]:
    """A client wired to a mocked HTTP layer, returned with that layer so tests can script and inspect its calls."""
    client = TelegramClient("test-token")
    http = AsyncMock(spec=httpx.AsyncClient)
    http.is_closed = False
    client._http = http
    return client, http


def ok_response(result: object = None) -> httpx.Response:
    """Build a mock Telegram API success response."""

    body = {"ok": True, "result": result or {}}
    return httpx.Response(200, json=body)


def error_response(code: int = 400, desc: str = "Bad Request") -> httpx.Response:
    body = {"ok": False, "error_code": code, "description": desc}
    return httpx.Response(code, json=body)
