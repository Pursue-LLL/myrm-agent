"""OpenAI request rules that depend on the model: the reasoning families and the parameters they refuse."""

from __future__ import annotations

from dataclasses import replace

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.toolkits.llms.transport import openai_chat, openai_responses
from myrm_agent_harness.toolkits.llms.transport.params import split_params
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

# Ids the catalog does not list, registered per test: one that can stop reasoning (GPT-5.1 and later) and one that cannot.
CAN_STOP = "gpt-5-test-can-stop"
ALWAYS_REASONS = "gpt-5-test-always"


@pytest.fixture(autouse=True)
def _models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})
    register_model(CAN_STOP, {"provider": "openai", "supports_none_reasoning_effort": True})
    register_model(ALWAYS_REASONS, {"provider": "openai", "supports_none_reasoning_effort": False})


def _chat(model: str, **params: object) -> dict[str, object]:
    route = resolve_route(f"openai/{model}", api_key="k")
    return openai_chat.prepare(route, [{"role": "user", "content": "hi"}], params).body


def _responses(model: str, **params: object) -> dict[str, object]:
    route = resolve_route(f"openai/{model}", api_key="k")
    return openai_responses.prepare(route, {"input": "hi", **params}).body


class TestTemperatureOnReasoningModels:
    def test_a_model_that_always_reasons_takes_only_the_default(self) -> None:
        assert "temperature" not in _chat(ALWAYS_REASONS, temperature=0.2)
        assert _chat(ALWAYS_REASONS, temperature=1)["temperature"] == 1

    def test_a_model_that_always_reasons_drops_it_whatever_the_effort(self) -> None:
        assert "temperature" not in _chat(ALWAYS_REASONS, temperature=0.2, reasoning_effort="none")

    @pytest.mark.parametrize("effort", [None, "none"])
    def test_a_model_that_can_stop_reasoning_keeps_it_while_it_does(self, effort: str | None) -> None:
        params = {"reasoning_effort": effort} if effort else {}
        assert _chat(CAN_STOP, temperature=0.2, **params)["temperature"] == 0.2

    @pytest.mark.parametrize("effort", ["minimal", "low", "medium", "high", "xhigh"])
    def test_a_model_that_can_stop_reasoning_drops_it_once_it_reasons(self, effort: str) -> None:
        assert "temperature" not in _chat(CAN_STOP, temperature=0.2, reasoning_effort=effort)

    def test_the_responses_api_states_effort_inside_the_reasoning_object(self) -> None:
        assert _responses(CAN_STOP, temperature=0.2, reasoning={"effort": "none"})["temperature"] == 0.2
        assert "temperature" not in _responses(CAN_STOP, temperature=0.2, reasoning={"effort": "high"})
        assert "temperature" not in _responses(ALWAYS_REASONS, temperature=0.2)

    def test_a_model_outside_the_reasoning_families_is_left_alone(self) -> None:
        assert _chat("gpt-4o", temperature=0.2, reasoning_effort="high")["temperature"] == 0.2

    def test_a_compatible_service_serving_the_same_name_is_left_alone(self) -> None:
        route = resolve_route(f"openrouter/{ALWAYS_REASONS}", api_key="k")
        body = openai_chat.prepare(route, [{"role": "user", "content": "hi"}], {"temperature": 0.2}).body
        assert body["temperature"] == 0.2


class TestTokenLimitOnReasoningModels:
    def test_max_tokens_becomes_max_completion_tokens(self) -> None:
        body = _chat(ALWAYS_REASONS, max_tokens=300)
        assert body["max_completion_tokens"] == 300
        assert "max_tokens" not in body

    def test_an_explicit_completion_limit_wins(self) -> None:
        body = _chat(ALWAYS_REASONS, max_tokens=300, max_completion_tokens=500)
        assert body["max_completion_tokens"] == 500
        assert "max_tokens" not in body

    def test_other_models_keep_max_tokens(self) -> None:
        body = _chat("gpt-4o", max_tokens=300)
        assert body["max_tokens"] == 300
        assert "max_completion_tokens" not in body


class TestAzureCredentials:
    def test_a_route_without_a_key_sends_no_credential_header(self) -> None:
        route = resolve_route("azure/my-deployment", api_base="https://res.openai.azure.com", api_key="k")

        request = openai_chat.prepare(replace(route, api_key=None), [{"role": "user", "content": "hi"}], {})

        assert request.url.startswith("https://res.openai.azure.com/openai/deployments/my-deployment/")
        assert "api-key" not in request.headers
        assert "Authorization" not in request.headers


class TestAzureApiVersion:
    """The version comes from the call, then ``AZURE_API_VERSION``, then the default of the API in use."""

    @staticmethod
    def _query(path: str, **params: object) -> dict[str, str]:
        route = resolve_route("azure/my-deployment", api_base="https://res.openai.azure.com", api_key="k")
        _, query, _ = openai_chat.openai_endpoint(route, split_params(params), path)
        return dict(query)

    def test_a_call_without_a_version_gets_the_default_of_the_api_it_uses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)
        assert self._query("/chat/completions") == {"api-version": "2024-10-21"}
        assert self._query("/responses") == {"api-version": "preview"}

    @pytest.mark.parametrize("path", ["/chat/completions", "/responses", "/embeddings"])
    def test_the_environment_names_the_version_when_the_call_does_not(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        monkeypatch.setenv("AZURE_API_VERSION", "2031-01-01")
        assert self._query(path) == {"api-version": "2031-01-01"}

    def test_a_version_in_the_call_wins_over_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_API_VERSION", "2031-01-01")
        assert self._query("/chat/completions", api_version="2032-02-02") == {"api-version": "2032-02-02"}

    def test_an_empty_variable_is_no_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_API_VERSION", "")
        assert self._query("/chat/completions") == {"api-version": "2024-10-21"}

    def test_the_variable_never_reaches_a_provider_that_has_no_api_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AZURE_API_VERSION", "2031-01-01")
        route = resolve_route("openai/gpt-4o", api_key="k")
        _, query, _ = openai_chat.openai_endpoint(route, split_params({}), "/chat/completions")
        assert not query
