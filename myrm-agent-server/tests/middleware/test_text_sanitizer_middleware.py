"""Tests for TextSanitizerMiddleware."""

import json

import pytest
from fastapi import FastAPI, Form, Request
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


def _tag(name: str, *, closing: bool = False) -> str:
    """Build an angle-bracket tag without spelling the literal form in source."""
    return chr(60) + ("/" if closing else "") + name + chr(62)


def _echo_client() -> TestClient:
    """App with the real middleware in front of JSON / raw-body / query / form echo routes."""
    app = FastAPI()
    app.add_middleware(TextSanitizerMiddleware)

    @app.post("/json")
    async def _json_echo(request: Request):
        return await request.json()

    @app.post("/raw")
    async def _raw_echo(request: Request):
        return {"body": (await request.body()).decode("utf-8", errors="replace")}

    @app.get("/query")
    async def _query_echo(q: str = ""):
        return {"q": q}

    @app.post("/form")
    async def _form_echo(message: str = Form(...)):
        return {"message": message}

    return TestClient(app)


@pytest.mark.parametrize("name", ["think", "thinking", "reasoning", "function_calls", "tool_call", "antml:invoke"])
def test_user_markup_survives_json_body(name: str) -> None:
    """Tags are user content (pasted snippets, prompts): only control characters are removed."""
    text = f"Fix this parser: {_tag(name)}x{_tag(name, closing=True)} done"
    response = _echo_client().post("/json", json={"message": text})
    assert response.json() == {"message": text}


def test_user_markup_survives_query_and_form() -> None:
    text = f"{_tag('think')}note{_tag('think', closing=True)}"
    client = _echo_client()
    assert client.get("/query", params={"q": text}).json() == {"q": text}
    assert client.post("/form", data={"message": text}).json() == {"message": text}


def test_control_characters_are_removed_around_markup() -> None:
    opening, closing = _tag("think"), _tag("think", closing=True)
    raw = f"a{opening}b\x00c<|endoftext|>d\x07{closing}"
    response = _echo_client().post("/json", json={"message": raw})
    assert response.json() == {"message": f"a{opening}bcd{closing}"}


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json; charset=utf-8",
        "application/json ;charset=utf-8",
        "APPLICATION/JSON",
        "application/merge-patch+json",
        "application/vnd.api+json",
    ],
)
def test_json_media_type_variants_are_sanitized(content_type: str) -> None:
    """FastAPI parses these as JSON, so the sanitizer must treat them as JSON too."""
    response = _echo_client().post("/json", content=b'{"m": "x\\u0000y"}', headers={"content-type": content_type})
    assert response.json() == {"m": "xy"}


def test_other_media_types_are_untouched() -> None:
    response = _echo_client().post("/raw", content=b"a\x01b", headers={"content-type": "text/plain"})
    assert response.json() == {"body": "a\x01b"}


def test_nested_lists_and_top_level_arrays_are_sanitized() -> None:
    response = _echo_client().post("/json", json=[["a\x00"], {"k": ["b\x01"]}])
    assert response.json() == [["a"], {"k": ["b"]}]


@pytest.mark.parametrize(
    "body",
    [b'{"a": "x\x01', b'{"n": ' + b"9" * 5000 + b"}", b"[" * 5000],
    ids=["truncated", "oversized-int", "deeply-nested"],
)
def test_unparseable_json_passes_through_for_the_route_to_judge(body: bytes) -> None:
    response = _echo_client().post("/raw", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 200
    assert response.json() == {"body": body.decode("utf-8", errors="replace")}
