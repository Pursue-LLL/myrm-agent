"""Tests for TextSanitizerMiddleware form data sanitization."""

from fastapi import FastAPI, Form, Request
from fastapi.testclient import TestClient

from app.middleware.text_sanitizer_middleware import TextSanitizerMiddleware


def test_sanitizes_form_data_single_field() -> None:
    """Test that form data with surrogates is sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(message: str = Form(...)):
        return {"message": message}

    client = TestClient(app)
    raw_data = "message=Hello\ud800World".encode("utf-8", errors="surrogatepass")
    response = client.post(
        "/test",
        content=raw_data,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "HelloWorld"}


def test_sanitizes_form_data_multiple_fields() -> None:
    """Test that multiple form fields are sanitized."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(username: str = Form(...), message: str = Form(...)):
        return {"username": username, "message": message}

    client = TestClient(app)
    raw_data = "username=John\ud800Doe&message=Test\udc00Message".encode("utf-8", errors="surrogatepass")
    response = client.post(
        "/test",
        content=raw_data,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert response.json() == {"username": "JohnDoe", "message": "TestMessage"}


def test_form_data_does_not_affect_json() -> None:
    """Test that form data sanitization does not affect JSON requests."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/test")
    async def _test_endpoint(request: Request):
        body = await request.json()
        return body

    client = TestClient(app)
    response = client.post("/test", json={"message": "Test"})
    assert response.status_code == 200
    assert response.json() == {"message": "Test"}
