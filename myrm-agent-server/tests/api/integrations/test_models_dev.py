"""Tests for GET /integrations/models-dev, the models.dev catalog proxy."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.integrations import models_dev
from app.core.utils.errors import StandardHTTPException, external_service_error
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_ENDPOINT = "/api/v1/integrations/models-dev"
_CATALOG = {"openai": {"id": "openai", "name": "OpenAI", "models": {"gpt-5": {"id": "gpt-5", "name": "GPT-5"}}}}

Handler = Callable[[httpx.Request], httpx.Response]


class _Upstream:
    """models.dev behind httpx's mock transport; records the requests it served."""

    def __init__(self, handler: Handler) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def client(self, **kwargs: object) -> httpx.AsyncClient:
        def serve(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self._handler(request)

        return httpx.AsyncClient(transport=httpx.MockTransport(serve), **kwargs)  # type: ignore[arg-type]


@contextmanager
def _upstream(handler: Handler) -> Iterator[_Upstream]:
    upstream = _Upstream(handler)
    with patch.object(models_dev, "create_httpx_client", upstream.client):
        yield upstream


def _serves_catalog(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_CATALOG)


def _raises(error: httpx.HTTPError) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    with patch.object(models_dev, "_catalog_cache", models_dev._CatalogCache()):
        yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


def test_the_catalog_comes_back_inside_the_success_envelope(client: TestClient) -> None:
    with _upstream(_serves_catalog) as upstream:
        response = client.get(_ENDPOINT)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"success": True, "code": 0, "data": _CATALOG}
    assert [str(request.url) for request in upstream.requests] == ["https://models.dev/api.json"]


def test_the_catalog_is_downloaded_once_within_the_ttl(client: TestClient) -> None:
    with _upstream(_serves_catalog) as upstream:
        first = client.get(_ENDPOINT)
        second = client.get(_ENDPOINT)

    assert first.content == second.content
    assert len(upstream.requests) == 1


def test_the_catalog_is_downloaded_again_once_the_ttl_has_passed(client: TestClient) -> None:
    with _upstream(_serves_catalog) as upstream, patch.object(models_dev, "_CACHE_TTL_S", 0.0):
        client.get(_ENDPOINT)
        client.get(_ENDPOINT)

    assert len(upstream.requests) == 2


async def test_requests_that_arrive_together_share_one_download() -> None:
    downloads = 0

    async def slow_download() -> bytes:
        nonlocal downloads
        downloads += 1
        await asyncio.sleep(0.02)
        return b'{"success":true,"code":0,"data":{}}'

    cache = models_dev._CatalogCache()
    with patch.object(models_dev, "_fetch_catalog_body", slow_download):
        bodies = await asyncio.gather(*(cache.get() for _ in range(5)))

    assert downloads == 1
    assert len(set(bodies)) == 1


async def test_requests_that_arrive_together_share_one_failed_download() -> None:
    downloads = 0

    async def failing_download() -> bytes:
        nonlocal downloads
        downloads += 1
        await asyncio.sleep(0.02)
        raise external_service_error("models.dev", "Failed to fetch models.dev data")

    cache = models_dev._CatalogCache()
    with patch.object(models_dev, "_fetch_catalog_body", failing_download):
        outcomes = await asyncio.gather(*(cache.get() for _ in range(5)), return_exceptions=True)

    assert downloads == 1
    assert all(isinstance(outcome, StandardHTTPException) and outcome.status_code == 502 for outcome in outcomes)


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        pytest.param(lambda request: httpx.Response(500, text="boom"), "Failed to fetch models.dev data", id="http-error"),
        pytest.param(_raises(httpx.ConnectError("refused")), "Failed to fetch models.dev data", id="connect-error"),
        pytest.param(_raises(httpx.ReadTimeout("slow")), "models.dev request timed out", id="timeout"),
        pytest.param(
            lambda request: httpx.Response(200, text="<html>captive portal</html>"),
            "models.dev returned an unexpected payload",
            id="not-json-object",
        ),
    ],
)
def test_an_unusable_upstream_answer_is_a_bad_gateway(client: TestClient, handler: Handler, message: str) -> None:
    with _upstream(handler):
        response = client.get(_ENDPOINT)

    assert response.status_code == 502
    assert message in response.text


def test_a_failed_download_is_not_cached(client: TestClient) -> None:
    answers = iter([httpx.Response(500), httpx.Response(200, json=_CATALOG)])

    with _upstream(lambda request: next(answers)) as upstream:
        failed = client.get(_ENDPOINT)
        recovered = client.get(_ENDPOINT)

    assert failed.status_code == 502
    assert recovered.json()["data"] == _CATALOG
    assert len(upstream.requests) == 2
