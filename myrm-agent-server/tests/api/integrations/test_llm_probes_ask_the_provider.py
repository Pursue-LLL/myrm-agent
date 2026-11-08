"""The settings-page probes ask the provider on every call: verify, check-reachability and speed-test.

The real chat model runs against a loopback provider that serves one API key. A key or endpoint the user has just edited
has to be judged by the provider, and so does a request that has not changed since an earlier success: no answer is kept
that could stand in for a mistyped key or hide a provider that has since gone away.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.integrations import llms
from tests.support.fake_chat_provider import FakeChatProvider, fake_chat_provider
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_RIGHT_KEY = "sk-right"
_MISTYPED_KEY = "sk-mistyped"
_MODEL = "openai/test-chat"
_VERIFY = "/api/v1/integrations/llm/verify"
_REACHABILITY = "/api/v1/integrations/llm/check-reachability"
_SPEED_TEST = "/api/v1/integrations/llm/speed-test"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app)


@pytest.fixture
def provider() -> Iterator[FakeChatProvider]:
    with fake_chat_provider(_RIGHT_KEY) as running:
        yield running


@pytest.fixture(autouse=True)
def empty_reachability_cache() -> Iterator[None]:
    # The reachability cache is the one cache a probe may be answered from; an empty one keeps the tests from answering
    # each other.
    llms._reachability_cache.clear()
    yield
    llms._reachability_cache.clear()


def _config(provider: FakeChatProvider, api_key: str, **extra: object) -> dict[str, object]:
    return {"model": _MODEL, "api_key": api_key, "base_url": provider.base_url, **extra}


def _reachability(client: TestClient, provider: FakeChatProvider, api_key: str) -> dict[str, object]:
    response = client.post(_REACHABILITY, json=_config(provider, api_key))
    assert response.status_code == 200, response.text
    data: dict[str, object] = response.json()["data"]
    return data


def _speed_test(client: TestClient, provider: FakeChatProvider, api_key: str) -> dict[str, object]:
    response = client.post(_SPEED_TEST, json={"models": [_config(provider, api_key)]})
    assert response.status_code == 200, response.text
    [result] = response.json()["data"]
    assert isinstance(result, dict)
    return result


def _authorizations(provider: FakeChatProvider) -> list[str | None]:
    return [seen.authorization for seen in provider.requests]


def test_verify_judges_a_mistyped_key_by_the_provider(client: TestClient, provider: FakeChatProvider) -> None:
    right = client.post(_VERIFY, json=_config(provider, _RIGHT_KEY))
    mistyped = client.post(_VERIFY, json=_config(provider, _MISTYPED_KEY))

    assert right.status_code == 200
    assert mistyped.status_code == 401
    assert "Incorrect API key provided" in mistyped.json()["message"]
    assert _authorizations(provider) == [f"Bearer {_RIGHT_KEY}", f"Bearer {_MISTYPED_KEY}"]


def test_reachability_reports_each_key_of_one_endpoint_on_its_own(client: TestClient, provider: FakeChatProvider) -> None:
    right = _reachability(client, provider, _RIGHT_KEY)
    mistyped = _reachability(client, provider, _MISTYPED_KEY)

    assert (right["reachable"], right["cached"]) == (True, False)
    assert (mistyped["reachable"], mistyped["cached"]) == (False, False)
    assert "Incorrect API key provided" in str(mistyped["error"])
    assert _authorizations(provider) == [f"Bearer {_RIGHT_KEY}", f"Bearer {_MISTYPED_KEY}"]


def test_reachability_asks_the_provider_again_once_its_own_window_has_passed(
    client: TestClient, provider: FakeChatProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llms.verify, "_REACHABILITY_CACHE_TTL_S", 0.0)

    first = _reachability(client, provider, _RIGHT_KEY)
    second = _reachability(client, provider, _RIGHT_KEY)

    assert (first["cached"], second["cached"]) == (False, False)
    assert len(provider.requests) == 2


def test_reachability_serves_the_same_request_from_its_own_cache_within_the_window(
    client: TestClient, provider: FakeChatProvider
) -> None:
    first = _reachability(client, provider, _RIGHT_KEY)
    second = _reachability(client, provider, _RIGHT_KEY)

    assert (first["cached"], second["cached"]) == (False, True)
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"model": "openai/other-chat"},
        {"api_key": _MISTYPED_KEY},
        {"base_url": "http://127.0.0.1:9/v1"},
        {"egress_proxy": "http://127.0.0.1:9"},
        {"temperature": 0.5},
        {"model_kwargs": {"extra_headers": {"X-Probe-Marker": "changed"}}},
    ],
    ids=lambda change: next(iter(change)),
)
def test_a_changed_part_of_the_request_is_a_new_reachability_question(change: dict[str, object]) -> None:
    request = llms.LLMVerifyRequest(model=_MODEL, api_key=_RIGHT_KEY, base_url="http://127.0.0.1:1/v1")

    assert llms._cache_key(request) != llms._cache_key(request.model_copy(update=change))


def test_the_reachability_cache_holds_a_digest_not_the_api_key(client: TestClient, provider: FakeChatProvider) -> None:
    _reachability(client, provider, _RIGHT_KEY)

    [cache_key] = llms._reachability_cache
    assert _RIGHT_KEY not in cache_key


def test_speed_test_times_every_run_against_the_provider(client: TestClient, provider: FakeChatProvider) -> None:
    first = _speed_test(client, provider, _RIGHT_KEY)
    second = _speed_test(client, provider, _RIGHT_KEY)

    assert (first["status"], second["status"]) == ("ok", "ok")
    assert len(provider.requests) == 2


@pytest.mark.parametrize("probe", ["verify", "reachability", "speed-test"])
def test_probes_keep_the_model_arguments_the_caller_sent(client: TestClient, provider: FakeChatProvider, probe: str) -> None:
    config = _config(provider, _RIGHT_KEY, model_kwargs={"extra_headers": {"X-Probe-Marker": "kept"}})

    if probe == "speed-test":
        client.post(_SPEED_TEST, json={"models": [config]})
    else:
        client.post(_VERIFY if probe == "verify" else _REACHABILITY, json=config)

    [seen] = provider.requests
    assert seen.headers["x-probe-marker"] == "kept"


def test_verify_asks_the_provider_again_for_a_request_it_already_made(client: TestClient, provider: FakeChatProvider) -> None:
    first = client.post(_VERIFY, json=_config(provider, _RIGHT_KEY))
    second = client.post(_VERIFY, json=_config(provider, _RIGHT_KEY))

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(provider.requests) == 2
