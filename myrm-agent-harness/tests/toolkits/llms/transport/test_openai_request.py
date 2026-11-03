"""OpenAI request rules that depend on the model: the reasoning families and the parameters they refuse."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.toolkits.llms.transport import openai_chat, openai_responses
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
