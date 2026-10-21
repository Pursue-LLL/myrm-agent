"""Tests for TextSanitizerMiddleware."""

import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.text_sanitizer_middleware import TextSanitizerMiddleware


def test_sanitizes_string_field() -> None:
    """Test that string fields with surrogates are sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(request: Request):
        body = await request.json()
        return body

    client = TestClient(app)
    raw_body = json.dumps({"message": "Hello\ud800World"}, ensure_ascii=False).encode("utf-8", errors="surrogatepass")
    response = client.post(
        "/test",
        content=raw_body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "HelloWorld"}


def test_sanitizes_nested_dict() -> None:
    """Test that nested dictionaries are recursively sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(request: Request):
        body = await request.json()
        return body

    client = TestClient(app)
    raw_body = json.dumps({"user": {"name": "Test\ud800User", "email": "test\udc00@example.com"}}, ensure_ascii=False).encode(
        "utf-8", errors="surrogatepass"
    )
    response = client.post(
        "/test",
        content=raw_body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"user": {"name": "TestUser", "email": "test@example.com"}}


def test_sanitizes_list_of_strings() -> None:
    """Test that lists of strings are sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(request: Request):
        body = await request.json()
        return body

    client = TestClient(app)
    raw_body = json.dumps({"messages": ["Hello\ud800", "World\udc00", "Test"]}, ensure_ascii=False).encode(
        "utf-8", errors="surrogatepass"
    )
    response = client.post(
        "/test",
        content=raw_body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"messages": ["Hello", "World", "Test"]}


def test_preserves_non_string_types() -> None:
    """Test that non-string types (numbers, booleans) are preserved."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(request: Request):
        body = await request.json()
        return body

    client = TestClient(app)
    response = client.post(
        "/test",
        json={"count": 42, "active": True, "price": 3.14, "tags": None},
    )
    assert response.status_code == 200
    assert response.json() == {"count": 42, "active": True, "price": 3.14, "tags": None}


def test_skips_non_json_requests() -> None:
    """Test that non-JSON requests are not sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint():
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/test", data="plain text")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_skips_get_requests() -> None:
    """Test that GET requests are not sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.get("/test")
    async def _test_endpoint():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
