"""Tests for TracingMiddleware — trace_id generation and context propagation."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.observability.tracing import TracingContext
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.middleware.observability import (
    TracingMiddleware,
    _extract_session_id,
    _parse_inbound_trace_id,
)


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

    async def test_inbound_x_trace_id_adopted(self) -> None:
        """When X-Trace-Id is a valid hex string, it should be adopted."""
        app = _make_app()
        inbound_id = "a1b2c3d4e5f67890abcdef1234567890"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/health", headers={"X-Trace-Id": inbound_id}
            )

        assert resp.status_code == 200
        assert resp.headers["x-trace-id"] == inbound_id
        assert resp.json()["trace_id"] == inbound_id

    async def test_inbound_traceparent_adopted(self) -> None:
        """W3C traceparent trace-id field should be extracted and adopted."""
        app = _make_app()
        w3c_trace_id = "0af7651916cd43dd8448eb211c80319c"
        traceparent = f"00-{w3c_trace_id}-b7ad6b7169203331-01"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/health", headers={"traceparent": traceparent}
            )

        assert resp.status_code == 200
        assert resp.headers["x-trace-id"] == w3c_trace_id
        assert resp.json()["trace_id"] == w3c_trace_id

    async def test_invalid_trace_id_falls_back_to_generated(self) -> None:
        """Non-hex or injection-attempt trace-id should be rejected."""
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/health",
                headers={"X-Trace-Id": "'; DROP TABLE logs; --"},
            )

        assert resp.status_code == 200
        trace = resp.headers["x-trace-id"]
        assert len(trace) == 32
        assert trace != "'; DROP TABLE logs; --"

    async def test_no_trace_header_generates_new(self) -> None:
        """Without any trace header, a fresh 32-char hex id is generated."""
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/health")

        trace = resp.headers["x-trace-id"]
        assert len(trace) == 32
        assert all(c in "0123456789abcdef" for c in trace)

    async def test_x_trace_id_takes_priority_over_traceparent(self) -> None:
        """X-Trace-Id should take priority when both headers are present."""
        app = _make_app()
        custom_id = "ff00ff00ff00ff00ff00ff00ff00ff00"
        traceparent = "00-0000000000000000aaaaaaaaaaaaaaaa-b7ad6b7169203331-01"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/health",
                headers={
                    "X-Trace-Id": custom_id,
                    "traceparent": traceparent,
                },
            )

        assert resp.headers["x-trace-id"] == custom_id


class TestParseInboundTraceId:
    """Unit tests for _parse_inbound_trace_id pure function."""

    def _make_request(self, headers: dict[str, str]) -> Request:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
        return Request(scope)

    def test_valid_x_trace_id(self) -> None:
        req = self._make_request({"X-Trace-Id": "abcdef1234567890"})
        assert _parse_inbound_trace_id(req) == "abcdef1234567890"

    def test_valid_traceparent(self) -> None:
        req = self._make_request(
            {"traceparent": "00-abcdef1234567890abcdef1234567890-0102030405060708-01"}
        )
        assert _parse_inbound_trace_id(req) == "abcdef1234567890abcdef1234567890"

    def test_empty_headers(self) -> None:
        req = self._make_request({})
        assert _parse_inbound_trace_id(req) is None

    def test_non_hex_rejected(self) -> None:
        req = self._make_request({"X-Trace-Id": "not-valid-hex!"})
        assert _parse_inbound_trace_id(req) is None

    def test_too_long_rejected(self) -> None:
        req = self._make_request({"X-Trace-Id": "a" * 65})
        assert _parse_inbound_trace_id(req) is None

    def test_single_char_hex_accepted(self) -> None:
        req = self._make_request({"X-Trace-Id": "f"})
        assert _parse_inbound_trace_id(req) == "f"

    def test_malformed_traceparent_rejected(self) -> None:
        req = self._make_request({"traceparent": "malformed"})
        assert _parse_inbound_trace_id(req) is None

    def test_mixed_case_hex_accepted(self) -> None:
        req = self._make_request({"X-Trace-Id": "AbCdEf0123456789"})
        assert _parse_inbound_trace_id(req) == "AbCdEf0123456789"

    def test_whitespace_in_trace_id_rejected(self) -> None:
        req = self._make_request({"X-Trace-Id": " abc123 "})
        assert _parse_inbound_trace_id(req) is None

    def test_empty_trace_id_rejected(self) -> None:
        req = self._make_request({"X-Trace-Id": ""})
        assert _parse_inbound_trace_id(req) is None

    def test_traceparent_too_few_parts_rejected(self) -> None:
        req = self._make_request({"traceparent": "00-abc123"})
        assert _parse_inbound_trace_id(req) is None

    def test_traceparent_non_hex_trace_id_rejected(self) -> None:
        req = self._make_request(
            {"traceparent": "00-not_hex_at_all!!!!!!!!!!!!!!!!!-0102030405060708-01"}
        )
        assert _parse_inbound_trace_id(req) is None

    def test_64_char_hex_accepted(self) -> None:
        long_id = "a" * 64
        req = self._make_request({"X-Trace-Id": long_id})
        assert _parse_inbound_trace_id(req) == long_id
