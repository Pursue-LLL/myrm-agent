"""A request carries only its own provider's secrets and endpoint; a proxy the caller names is used and never sent.

Provider configuration lives in environment variables, so the property that matters is what an environment holding
*every* provider's variables does to one call: it must pick up that provider's key, endpoint and version and nothing
of the others'. A proxy is the caller's own routing choice: it reaches the HTTP client of every wire and none of the
request the provider sees.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

import pytest

from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_messages,
    bedrock_converse,
    gemini_generate,
    http,
    ollama_chat,
    openai_chat,
    openai_responses,
)
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest, asend_json, send_json
from myrm_agent_harness.toolkits.llms.transport.profile import PROFILES, Route, resolve_route
from tests.support.forward_proxy import forward_proxy

_MESSAGES = [{"role": "user", "content": "hi"}]
_PREPARE: dict[str, Callable[[Route, list[dict[str, str]], Mapping[str, object]], PreparedRequest]] = {
    "openai_chat": openai_chat.prepare,
    "azure_openai": openai_chat.prepare,
    "anthropic": anthropic_messages.prepare,
    "gemini": gemini_generate.prepare,
    "ollama": ollama_chat.prepare,
    "bedrock": bedrock_converse.prepare,
}
_KEYS = tuple(name for profile in PROFILES.values() for name in profile.api_key_env)
_BASES = tuple(name for profile in PROFILES.values() for name in profile.api_base_env)
_VERSIONS = tuple(name for profile in PROFILES.values() for name in profile.api_version_env)
_REGION_VARIABLES = ("AWS_REGION_NAME", "AWS_REGION", "AWS_DEFAULT_REGION")
# The providers whose endpoint is not in the profile: it depends on the region.
_DEFAULT_HOSTS = {"bedrock": "bedrock-runtime.us-west-2.amazonaws.com"}
_CALLS = [(provider, "chat") for provider in PROFILES] + [
    (provider, "responses") for provider, profile in PROFILES.items() if profile.responses
]


def _secret(name: str) -> str:
    return f"secret-{name}-end"


def _version(name: str) -> str:
    return f"version-{name}-end"


def _host(name: str) -> str:
    return f"base-{name.lower().replace('_', '-')}.invalid"


def _prepare(provider: str, call: str) -> PreparedRequest:
    route = resolve_route(f"{provider}/some-model")
    if call == "responses":
        return openai_responses.prepare(route, {"input": "hi"})
    return _PREPARE[route.profile.wire](route, _MESSAGES, {})


def _seen_by_the_provider(request: PreparedRequest) -> str:
    return json.dumps([request.url, dict(request.query), dict(request.headers), request.body], default=str)


@pytest.fixture
def every_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _KEYS:
        monkeypatch.setenv(name, _secret(name))
    for name in _BASES:
        monkeypatch.setenv(name, f"http://{_host(name)}")
    for name in _VERSIONS:
        monkeypatch.setenv(name, _version(name))
    for name in _REGION_VARIABLES:
        monkeypatch.delenv(name, raising=False)


class TestEnvironmentOfSeveralProviders:
    def test_every_variable_belongs_to_one_provider(self) -> None:
        names = [*_KEYS, *_BASES, *_VERSIONS]

        assert len(names) == len(set(names))

    def test_every_wire_of_the_profiles_is_covered_here(self) -> None:
        assert {profile.wire for profile in PROFILES.values()} <= set(_PREPARE)

    @pytest.mark.usefixtures("every_variable")
    @pytest.mark.parametrize(("provider", "call"), _CALLS, ids=[f"{p}-{c}" for p, c in _CALLS])
    def test_a_call_carries_only_the_secrets_of_its_own_provider(self, provider: str, call: str) -> None:
        profile = PROFILES[provider]

        carried = _seen_by_the_provider(_prepare(provider, call))

        expected = {profile.api_key_env[0]} if profile.api_key_env else set()
        assert {name for name in _KEYS if _secret(name) in carried} == expected
        assert {name for name in _VERSIONS if _version(name) in carried} == (
            {profile.api_version_env[0]} if call == "chat" and profile.api_version_env else set()
        )

    @pytest.mark.usefixtures("every_variable")
    @pytest.mark.parametrize(("provider", "call"), _CALLS, ids=[f"{p}-{c}" for p, c in _CALLS])
    def test_a_call_goes_to_the_endpoint_of_its_own_provider(self, provider: str, call: str) -> None:
        profile = PROFILES[provider]

        host = urlsplit(_prepare(provider, call).url).hostname

        if profile.api_base_env:
            assert host == _host(profile.api_base_env[0])
        else:
            assert host == (urlsplit(profile.base_url).hostname if profile.base_url else _DEFAULT_HOSTS[provider])


_PROXY = "http://proxy-user:proxy-pass@proxy.test:3128"
_PROXIED = [
    ("openai/gpt-4o", None),
    ("azure/gpt-4o", "https://resource.openai.azure.com"),
    ("anthropic/claude-sonnet-4-5", None),
    ("gemini/gemini-2.5-pro", None),
    ("ollama/llama3.1", None),
    ("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", None),
]


class TestExplicitProxy:
    @pytest.mark.parametrize(("model", "api_base"), _PROXIED, ids=[model for model, _ in _PROXIED])
    def test_every_wire_hands_the_proxy_to_the_http_layer_and_keeps_it_out_of_the_request(
        self, model: str, api_base: str | None
    ) -> None:
        route = resolve_route(model, api_key="key", api_base=api_base)

        request = _PREPARE[route.profile.wire](route, _MESSAGES, {"proxy": _PROXY})

        assert request.proxy == _PROXY
        assert "proxy-pass" not in _seen_by_the_provider(request)

    def test_the_responses_wire_hands_the_proxy_over_as_well(self) -> None:
        route = resolve_route("openai/gpt-5.4", api_key="key")

        request = openai_responses.prepare(route, {"input": "hi", "proxy": _PROXY})

        assert request.proxy == _PROXY
        assert "proxy-pass" not in _seen_by_the_provider(request)

    def test_a_call_that_names_no_proxy_uses_none(self) -> None:
        route = resolve_route("openai/gpt-4o", api_key="key")

        assert openai_chat.prepare(route, _MESSAGES, {}).proxy is None


_TARGET = "http://llm.invalid/v1/chat/completions"  # a host that exists nowhere: only a proxy can answer for it


def _call(proxy: str) -> PreparedRequest:
    return PreparedRequest(provider="openai", url=_TARGET, headers={}, body={"model": "m"}, timeout=5, proxy=proxy)


class TestProxyReachesTheNetwork:
    """The shared HTTP clients really connect through the proxy a call names, in both the sync and the async path."""

    def test_a_sync_call_goes_through_the_proxy(self) -> None:
        with forward_proxy() as proxy:
            try:
                assert send_json(_call(proxy.url)) == {"ok": True}
            finally:
                asyncio.run(http.aclose_clients())

            assert proxy.targets == [_TARGET]

    async def test_an_async_call_goes_through_the_proxy(self) -> None:
        with forward_proxy() as proxy:
            try:
                assert await asend_json(_call(proxy.url)) == {"ok": True}
            finally:
                await http.aclose_clients()

            assert proxy.targets == [_TARGET]
