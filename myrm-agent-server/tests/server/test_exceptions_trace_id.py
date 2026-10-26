"""Every error the real handlers answer with names the request it belongs to.

[INPUT]
- app.middleware.observability::TracingMiddleware (POS: binds the request's trace id and answers with X-Trace-Id)
- app.core.utils.errors / app.server.exceptions (POS: the handlers the real application registers)

[OUTPUT]
- Tests proving the ``X-Trace-Id`` header and the ``error.trace_id`` of an error body are one id for server
  faults, for the unhandled-exception handler that runs outside the middleware, and for validation details;
  and that a plain client error stays a message.

[POS]
The real middleware and the real handlers on a small application: the handler outside the middleware is the
one place the id can only come from the request, so it is exercised end to end.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.utils.errors import MyrmError, field_validation_error
from app.middleware.observability import TracingMiddleware
from app.schemas.responses import BusinessCode
from tests.support.minimal_app import build_minimal_app

_INBOUND_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


def _build_app() -> FastAPI:
    app = build_minimal_app()

    @app.get("/client-error")
    async def _client_error() -> None:
        raise MyrmError(BusinessCode.RESOURCE_NOT_FOUND, "Nothing here")

    @app.get("/server-fault")
    async def _server_fault() -> None:
        raise MyrmError(BusinessCode.DB_QUERY_ERROR, "Query failed")

    @app.get("/crash")
    async def _crash() -> None:
        raise RuntimeError("boom")

    @app.get("/attribute-error")
    async def _attribute_error() -> None:
        raise AttributeError("'str' object has no attribute 'id'")

    @app.get("/invalid")
    async def _invalid() -> None:
        raise field_validation_error({"name": "required"})

    app.add_middleware(TracingMiddleware)
    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.mark.parametrize("path", ["/server-fault", "/crash", "/attribute-error"])
async def test_server_fault_names_its_request_in_header_and_body(client: AsyncClient, path: str) -> None:
    response = await client.get(path, headers={"X-Trace-Id": _INBOUND_TRACE_ID})

    assert response.status_code >= 500
    assert response.headers["x-trace-id"] == _INBOUND_TRACE_ID
    assert response.json()["error"]["trace_id"] == _INBOUND_TRACE_ID


async def test_unhandled_exception_without_inbound_id_still_answers_with_one_id(client: AsyncClient) -> None:
    response = await client.get("/crash")

    header = response.headers["x-trace-id"]
    assert len(header) == 32
    assert response.json()["error"]["trace_id"] == header


async def test_client_error_stays_a_message_but_still_carries_the_header(client: AsyncClient) -> None:
    response = await client.get("/client-error", headers={"X-Trace-Id": _INBOUND_TRACE_ID})

    assert response.status_code == 404
    assert response.headers["x-trace-id"] == _INBOUND_TRACE_ID
    assert response.json()["error"] is None


async def test_unknown_route_stays_a_message_but_still_carries_the_header(client: AsyncClient) -> None:
    response = await client.get("/nowhere", headers={"X-Trace-Id": _INBOUND_TRACE_ID})

    assert response.status_code == 404
    assert response.headers["x-trace-id"] == _INBOUND_TRACE_ID
    assert response.json()["error"] is None


async def test_validation_details_carry_the_request_trace_id(client: AsyncClient) -> None:
    response = await client.get("/invalid", headers={"X-Trace-Id": _INBOUND_TRACE_ID})

    assert response.status_code == 400
    assert response.headers["x-trace-id"] == _INBOUND_TRACE_ID
    assert response.json()["detail"]["error"]["trace_id"] == _INBOUND_TRACE_ID
