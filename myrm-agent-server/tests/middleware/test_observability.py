"""Tests for TracingMiddleware — trace_id generation and context propagation."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from myrm_agent_harness.observability.tracing import TracingContext

from app.middleware.observability import TracingMiddleware, _extract_session_id


def _make_app() -> Starlette:
    """Minimal Starlette app with TracingMiddleware for testing."""

    async def echo_trace(request: Request) -> JSONResponse:
        return JSONResponse({
            "trace_id": TracingContext.get_trace_id(),
            "session_id": TracingContext.get_session_id(),
        })

    app = Starlette(routes=[
        Route("/api/sessions/{sid}/messages", echo_trace),
        Route("/api/health", echo_trace),
    ])
    app.add_middleware(TracingMiddleware)
    return app


class TestExtractSessionId:
    def test_with_session_path(self) -> None:
        assert _extract_session_id("/api/sessions/abc-123/messages") == "abc-123"

    def test_with_session_path_no_trailing(self) -> None:
        assert _extract_session_id("/api/sessions/abc-123") == "abc-123"

    def test_non_session_path(self) -> None:
        assert _extract_session_id("/api/health") == "-"

    def test_empty_path(self) -> None:
        assert _extract_session_id("/") == "-"

    def test_trailing_slash_only(self) -> None:
        assert _extract_session_id("/api/sessions/") == ""

    def test_uuid_session_id(self) -> None:
        sid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert _extract_session_id(f"/api/sessions/{sid}/messages") == sid


@pytest.mark.asyncio
class TestTracingMiddleware:
    async def test_response_has_trace_id_header(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/health")

        assert resp.status_code == 200
        trace_header = resp.headers.get("x-trace-id")
        assert trace_header is not None
        assert len(trace_header) == 32

    async def test_trace_id_propagated_to_handler(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/health")

        data = resp.json()
        assert data["trace_id"] == resp.headers["x-trace-id"]
        assert data["session_id"] == "-"

    async def test_session_id_extracted_from_path(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/sessions/my-sess-42/messages")

        data = resp.json()
        assert data["session_id"] == "my-sess-42"

    async def test_unique_trace_ids_per_request(self) -> None:
        app = _make_app()
        ids: list[str] = []
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(5):
                resp = await client.get("/api/health")
                ids.append(resp.headers["x-trace-id"])

        assert len(set(ids)) == 5

    async def test_context_reset_after_request(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/api/health")

        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"

    async def test_post_request_has_trace_header(self) -> None:
        async def handle_post(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True}, status_code=201)

        app = Starlette(routes=[Route("/api/data", handle_post, methods=["POST"])])
        app.add_middleware(TracingMiddleware)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/data", json={"x": 1})

        assert resp.status_code == 201
        assert "x-trace-id" in resp.headers
        assert len(resp.headers["x-trace-id"]) == 32

    async def test_exception_still_resets_context(self) -> None:
        async def raise_error(_request: Request) -> JSONResponse:
            raise RuntimeError("boom")

        app = Starlette(routes=[Route("/api/fail", raise_error)])
        app.add_middleware(TracingMiddleware)

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/fail")

        assert resp.status_code == 500
        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"
