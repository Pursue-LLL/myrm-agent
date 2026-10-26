"""ima transport: envelope spellings, error classification, retry policy, fixed origin and credential headers."""

from __future__ import annotations

import httpx
import pytest

from app.services.wiki.source_sync.ima import transport as transport_module
from app.services.wiki.source_sync.ima.errors import (
    ImaAuthError,
    ImaPermanentError,
    ImaRateLimitError,
    ImaTransientError,
)
from app.services.wiki.source_sync.ima.models import ImaCredentials
from app.services.wiki.source_sync.ima.transport import WIKI_PREFIX, ImaTransport, unwrap_envelope

CREDENTIALS = ImaCredentials(client_id="client-1", api_key="secret-key")


def _transport(handler: httpx.MockTransport) -> ImaTransport:
    return ImaTransport(CREDENTIALS, transport=handler)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport_module, "_TRANSIENT_BACKOFF_S", (0.0, 0.0))


@pytest.mark.parametrize(
    "payload",
    [
        {"retcode": 0, "errmsg": "ok", "data": {"value": 1}},
        {"code": 0, "msg": "ok", "data": {"value": 1}},
    ],
)
def test_both_envelope_spellings_unwrap_to_data(payload: dict[str, object]) -> None:
    assert unwrap_envelope(payload, status_code=200) == {"value": 1}


def test_success_without_data_yields_empty_object() -> None:
    assert unwrap_envelope({"retcode": 0}, status_code=200) == {}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"retcode": 20004, "errmsg": "bad key"}, ImaAuthError),
        ({"code": 110030, "msg": "bad key"}, ImaAuthError),
        ({"retcode": 20002}, ImaRateLimitError),
        ({"code": 110010}, ImaTransientError),
        ({"retcode": 999, "errmsg": "nope"}, ImaPermanentError),
        ({"data": {}}, ImaPermanentError),
        ([], ImaPermanentError),
    ],
)
def test_envelope_codes_map_to_typed_failures(payload: object, expected: type[Exception]) -> None:
    with pytest.raises(expected):
        unwrap_envelope(payload, status_code=200)


async def test_post_sends_credentials_to_the_fixed_origin() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"retcode": 0, "data": {"ok": True}})

    async with _transport(httpx.MockTransport(handler)) as ima:
        assert await ima.post(WIKI_PREFIX, "get_knowledge_list", {"cursor": ""}) == {"ok": True}

    request = seen[0]
    assert str(request.url) == "https://ima.qq.com/openapi/wiki/v1/get_knowledge_list"
    assert request.headers["ima-openapi-clientid"] == "client-1"
    assert request.headers["ima-openapi-apikey"] == "secret-key"


async def test_transient_http_errors_are_retried_then_succeed() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"retcode": 0, "data": {}})

    async with _transport(httpx.MockTransport(handler)) as ima:
        await ima.post(WIKI_PREFIX, "m", {})
    assert attempts == 3


async def test_transient_failures_surface_after_the_retry_budget() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("boom")

    async with _transport(httpx.MockTransport(handler)) as ima:
        with pytest.raises(ImaTransientError):
            await ima.post(WIKI_PREFIX, "m", {})
    assert attempts == 3


@pytest.mark.parametrize(("status", "expected"), [(401, ImaAuthError), (403, ImaAuthError), (404, ImaPermanentError)])
async def test_non_retryable_http_statuses_fail_immediately(status: int, expected: type[Exception]) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status)

    async with _transport(httpx.MockTransport(handler)) as ima:
        with pytest.raises(expected):
            await ima.post(WIKI_PREFIX, "m", {})
    assert attempts == 1


async def test_rate_limit_carries_the_server_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "120"})

    async with _transport(httpx.MockTransport(handler)) as ima:
        with pytest.raises(ImaRateLimitError) as caught:
            await ima.post(WIKI_PREFIX, "m", {})
    assert caught.value.retry_after_s == 120.0


async def test_non_json_body_is_a_permanent_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    async with _transport(httpx.MockTransport(handler)) as ima:
        with pytest.raises(ImaPermanentError):
            await ima.post(WIKI_PREFIX, "m", {})


def test_credentials_repr_hides_the_api_key() -> None:
    assert "secret-key" not in repr(CREDENTIALS)
