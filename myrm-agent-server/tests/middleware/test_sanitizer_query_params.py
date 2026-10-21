"""Tests for TextSanitizerMiddleware query parameter sanitization."""

import json
from urllib.parse import quote_plus

from fastapi import FastAPI, Query, Request
from fastapi.testclient import TestClient

from app.middleware.text_sanitizer_middleware import TextSanitizerMiddleware


def test_sanitizes_get_query_string() -> None:
    """Test that GET query parameters with surrogates are sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.get("/test")
    async def _test_endpoint(q: str = Query(default="")):
        return {"query": q}

    client = TestClient(app)
    query_string = "Hello\ud800World".encode("utf-8", errors="surrogatepass")
    url = f"/test?q={quote_plus(query_string.decode('utf-8', errors='replace'))}"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {"query": "HelloWorld"}


def test_sanitizes_multiple_query_params() -> None:
    """Test that multiple query parameters are sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.get("/test")
    async def _test_endpoint(q1: str = Query(default=""), q2: str = Query(default="")):
        return {"q1": q1, "q2": q2}

    client = TestClient(app)
    q1_bytes = "A\ud800B".encode("utf-8", errors="surrogatepass")
    q2_bytes = "C\udc00D".encode("utf-8", errors="surrogatepass")
    q1_encoded = quote_plus(q1_bytes.decode("utf-8", errors="replace"))
    q2_encoded = quote_plus(q2_bytes.decode("utf-8", errors="replace"))
    url = f"/test?q1={q1_encoded}&q2={q2_encoded}"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {"q1": "AB", "q2": "CD"}


def test_sanitizes_post_query_params() -> None:
    """Test that POST requests with query params are also sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(q: str = Query(default=""), request: Request = None):
        body = await request.json() if request else {}
        return {"query": q, "body": body}

    client = TestClient(app)
    query_bytes = "Hello\ud800World".encode("utf-8", errors="surrogatepass")
    query_encoded = quote_plus(query_bytes.decode("utf-8", errors="replace"))
    url = f"/test?q={query_encoded}"
    response = client.post(
        url,
        content=json.dumps({"message": "Test"}).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"query": "HelloWorld", "body": {"message": "Test"}}
