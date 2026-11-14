"""Tests for the provider identity that reasoning-parameter normalization reads.

The ``openai/`` segment of a model id names the wire protocol, so SiliconFlow, OpenCode Go and custom endpoints all
carry their own models behind it. The route facts (provider, bare model id, first-party endpoint, body shape) are
what the reasoning rules decide on.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.core.reasoning_route import ReasoningRoute, resolve_reasoning_route

_GATEWAY = "https://opencode.ai/zen/go/v1"


class TestResolveReasoningRoute:
    def test_first_party_openai_without_a_base_url(self) -> None:
        assert resolve_reasoning_route("openai/gpt-4o") == ReasoningRoute(
            provider="openai", model="gpt-4o", first_party=True, openai_body=True
        )

    def test_custom_endpoint_behind_the_openai_segment_is_not_first_party(self) -> None:
        route = resolve_reasoning_route("openai/deepseek-v4.1-flash", _GATEWAY)

        assert route == ReasoningRoute(
            provider="openai", model="deepseek-v4.1-flash", first_party=False, openai_body=True
        )

    def test_model_id_is_lowercased_and_keeps_inner_path(self) -> None:
        route = resolve_reasoning_route("openai/Qwen/Qwen3-32B", "https://api.siliconflow.cn/v1")

        assert route is not None
        assert route.model == "qwen/qwen3-32b"

    def test_bare_model_on_an_unknown_host_is_openai_compatible(self) -> None:
        route = resolve_reasoning_route("deepseek-v4.1-flash", "http://127.0.0.1:1/v1")

        assert route is not None
        assert route.provider == "openai_compatible"
        assert route.openai_body is True

    def test_anthropic_does_not_speak_an_openai_body(self) -> None:
        route = resolve_reasoning_route("anthropic/claude-sonnet-4-5")

        assert route is not None
        assert route.openai_body is False

    def test_azure_speaks_an_openai_body(self) -> None:
        route = resolve_reasoning_route("azure/gpt-4o", "https://res.openai.azure.com")

        assert route is not None
        assert (route.provider, route.openai_body) == ("azure", True)

    def test_explicit_provider_overrides_the_segment(self) -> None:
        route = resolve_reasoning_route("deepseek-chat", custom_llm_provider="deepseek")

        assert route is not None
        assert route.provider == "deepseek"

    @pytest.mark.parametrize("model", ["nonexistent/foo", "plain-model-without-endpoint"])
    def test_unresolvable_model_returns_none(self, model: str) -> None:
        assert resolve_reasoning_route(model) is None
