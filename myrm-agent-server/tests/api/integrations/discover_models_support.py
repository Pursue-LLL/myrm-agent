"""Shared fixtures for the discover-models endpoint tests.

[POS]
The app, the HTTP-client double and the response builder every discover-models test module uses, so a module stays
below the file-size limit without copying them.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

_APP = build_minimal_app(preset="integrations")


@asynccontextmanager
async def mock_httpx_client(*_args: object, **_kwargs: object) -> AsyncIterator[object]:
    yield object()


def json_response(payload: object, url: str = "http://127.0.0.1:8899/v1/models", status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", url),
    )


@contextmanager
def discovery_test_client() -> Iterator[TestClient]:
    """A client whose requests count as loopback, which is what local mode trusts."""
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True), TestClient(_APP) as client:
        yield client
