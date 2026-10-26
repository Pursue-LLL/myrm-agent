"""GenAI provider label of a model configuration (asked of LiteLLM, never guessed from the string)."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model.model_provider import model_provider_name


@pytest.mark.parametrize(
    ("model", "api_base", "custom_provider", "expected"),
    [
        ("gpt-4o-mini", None, None, "openai"),
        ("anthropic/claude-3-5-sonnet-20241022", None, None, "anthropic"),
        ("bedrock/anthropic.claude-3-haiku", None, None, "aws.bedrock"),
        ("gemini/gemini-2.0-flash", None, None, "gcp.gemini"),
        ("vertex_ai/gemini-2.0", None, None, "gcp.vertex_ai"),
        ("xai/grok-4", None, None, "x_ai"),
        ("openai/qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1", None, "openai"),
        ("grok-4", None, "xai", "x_ai"),
        ("ollama/qwen2.5", "http://localhost:11434", None, "ollama"),
    ],
)
def test_provider_is_resolved_the_way_litellm_routes_the_call(
    model: str, api_base: str | None, custom_provider: str | None, expected: str
) -> None:
    assert model_provider_name(model, api_base, custom_provider) == expected


def test_an_unresolvable_model_is_labelled_unknown_rather_than_failing() -> None:
    assert model_provider_name("totally-unknown-model", None, None) == "unknown"


def test_resolution_happens_once_per_configuration() -> None:
    model_provider_name.cache_clear()

    model_provider_name("gpt-4o-mini", None, None)
    model_provider_name("gpt-4o-mini", None, None)

    info = model_provider_name.cache_info()
    assert (info.misses, info.hits) == (1, 1)
