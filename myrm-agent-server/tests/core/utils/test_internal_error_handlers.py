"""An AttributeError or TypeError raised inside a route answers with a generic 500 envelope.

The envelope never repeats the exception text; only debug mode adds the exception type and traceback.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.utils.errors import register_exception_handlers

CASES = [
    pytest.param("/attribute-error", "AttributeError", "Data type mismatch detected. Please contact support.", id="attribute"),
    pytest.param("/type-error", "TypeError", "Type error detected. Please contact support.", id="type"),
]


def _app(*, debug: bool) -> FastAPI:
    app = FastAPI()
    with patch("app.config.env.is_debug_mode", return_value=debug):
        register_exception_handlers(app)

    @app.get("/attribute-error")
    async def _attribute_error() -> None:
        raise AttributeError("'str' object has no attribute 'secret_token'")

    @app.get("/type-error")
    async def _type_error() -> None:
        raise TypeError("'NoneType' object is not subscriptable: secret_token")

    return app


async def _get(app: FastAPI, path: str) -> tuple[int, dict[str, object]]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)
    return response.status_code, response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "exception_type", "message"), CASES)
async def test_production_answers_with_a_generic_message_and_no_traceback(path: str, exception_type: str, message: str) -> None:
    status_code, body = await _get(_app(debug=False), path)

    assert status_code == 500
    assert body["message"] == message
    assert "secret_token" not in str(body)
    assert exception_type not in str(body)
    assert "traceback" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "exception_type", "message"), CASES)
async def test_debug_mode_adds_the_exception_type_and_traceback(path: str, exception_type: str, message: str) -> None:
    status_code, body = await _get(_app(debug=True), path)

    assert status_code == 500
    assert body["message"] == message
    assert body["exception_type"] == exception_type
    assert body["traceback"]
