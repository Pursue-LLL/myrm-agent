"""Unit tests for FastAPI Request/Response adapters."""

from __future__ import annotations

import pytest
from fastapi.responses import Response

from app.channels.implementations.fastapi.adapters import (
    FastAPIRequestAdapter,
    FastAPIResponseAdapter,
)


@pytest.fixture
def mock_fastapi_request():
    """Create a mock FastAPI Request."""

    class MockClient:
        host = "192.168.1.1"

    class MockURL:
        path = "/api/channels/telegram/webhook"

    class MockRequest:
        method = "POST"
        url = MockURL()
        client = MockClient()

        def __init__(self):
            self._headers = {
                "content-type": "application/json",
                "x-forwarded-for": "203.0.113.1, 198.51.100.1",
                "x-real-ip": "203.0.113.1",
            }
            self._query_params = {"key": "value", "foo": "bar"}
            self._body = b'{"test": "data"}'

        @property
        def headers(self):
            return self._headers

        @property
        def query_params(self):
            return self._query_params

        async def body(self):
            return self._body

        async def json(self):
            return {"test": "data"}

    return MockRequest()


class TestFastAPIRequestAdapter:
    """Test FastAPIRequestAdapter."""

    def test_adapt_method(self, mock_fastapi_request):
        """Test method adaptation."""
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        assert adapted.method == "POST"

    def test_adapt_path(self, mock_fastapi_request):
        """Test path adaptation."""
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        assert adapted.path == "/api/channels/telegram/webhook"

    def test_adapt_headers(self, mock_fastapi_request):
        """Test headers adaptation."""
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        headers = adapted.headers
        assert headers["content-type"] == "application/json"
        assert "x-forwarded-for" in headers

    def test_adapt_query_params(self, mock_fastapi_request):
        """Test query parameters adaptation."""
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        params = adapted.query_params
        assert params["key"] == "value"
        assert params["foo"] == "bar"

    def test_adapt_client_ip_with_x_forwarded_for(self, mock_fastapi_request):
        """Test client IP extraction from X-Forwarded-For header."""
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        assert adapted.client_ip == "203.0.113.1"

    def test_adapt_client_ip_with_x_real_ip(self, mock_fastapi_request):
        """Test client IP extraction from X-Real-IP header (fallback)."""
        mock_fastapi_request._headers.pop("x-forwarded-for")
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        assert adapted.client_ip == "203.0.113.1"

    def test_adapt_client_ip_with_direct_connection(self, mock_fastapi_request):
        """Test client IP extraction from direct connection (fallback)."""
        mock_fastapi_request._headers.pop("x-forwarded-for")
        mock_fastapi_request._headers.pop("x-real-ip")
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        assert adapted.client_ip == "192.168.1.1"

    def test_adapt_client_ip_with_no_client(self, mock_fastapi_request):
        """Test client IP extraction when client is None."""
        mock_fastapi_request._headers.pop("x-forwarded-for")
        mock_fastapi_request._headers.pop("x-real-ip")
        mock_fastapi_request.client = None
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        assert adapted.client_ip == "unknown"

    @pytest.mark.asyncio
    async def test_adapt_body(self, mock_fastapi_request):
        """Test body adaptation."""
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        body = await adapted.body()
        assert body == b'{"test": "data"}'

    @pytest.mark.asyncio
    async def test_adapt_json(self, mock_fastapi_request):
        """Test JSON parsing."""
        adapter = FastAPIRequestAdapter()
        adapted = adapter.adapt(mock_fastapi_request)
        json_data = await adapted.json()
        assert json_data == {"test": "data"}


class TestFastAPIResponseAdapter:
    """Test FastAPIResponseAdapter."""

    def test_adapt_status_code(self):
        """Test status code adaptation."""

        class MockResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            body = b'{"ok": true}'

        adapter = FastAPIResponseAdapter()
        response = adapter.adapt(MockResponse())
        assert isinstance(response, Response)
        assert response.status_code == 200

    def test_adapt_headers(self):
        """Test headers adaptation."""

        class MockResponse:
            status_code = 201
            headers = {"x-custom-header": "value"}
            body = b"created"

        adapter = FastAPIResponseAdapter()
        response = adapter.adapt(MockResponse())
        assert response.headers["x-custom-header"] == "value"

    def test_adapt_body(self):
        """Test body adaptation."""

        class MockResponse:
            status_code = 200
            headers = {}
            body = b"test content"

        adapter = FastAPIResponseAdapter()
        response = adapter.adapt(MockResponse())
        assert response.body == b"test content"

    def test_adapt_error_response(self):
        """Test error response adaptation."""

        class MockErrorResponse:
            status_code = 500
            headers = {}
            body = b'{"error": "Internal server error"}'

        adapter = FastAPIResponseAdapter()
        response = adapter.adapt(MockErrorResponse())
        assert response.status_code == 500
        assert response.body == b'{"error": "Internal server error"}'
