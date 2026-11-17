"""Unit tests for wire defaults: MiniMax M3 reasoning effort and Vercel AI Gateway attribution headers."""

from __future__ import annotations

import pytest

from app.core.types import ModelConfig
from app.core.wire.defaults import apply_wire_defaults
from app.core.wire.enrich import enrich_model_config


def test_apply_wire_defaults_vercel_provider_id() -> None:
    result = apply_wire_defaults(
        model="claude-3-5-sonnet",
        model_kwargs=None,
        wire_protocol="chat_completions",
        provider_id="vercel_ai_gateway",
    )
    headers = result.get("extra_headers")
    assert isinstance(headers, dict)
    assert headers["HTTP-Referer"] == "https://myrm.ai"
    assert headers["X-Title"] == "Myrm Agent"
    assert headers["User-Agent"] == "Myrm/1.0 (Vercel-AI-Gateway-Client)"
    assert result["custom_llm_provider"] == "openai"


def test_apply_wire_defaults_vercel_base_url() -> None:
    result = apply_wire_defaults(
        model="deepseek-chat",
        model_kwargs=None,
        wire_protocol="chat_completions",
        base_url="https://ai-gateway.vercel.sh/v1",
    )
    headers = result.get("extra_headers")
    assert isinstance(headers, dict)
    assert headers["HTTP-Referer"] == "https://myrm.ai"
    assert headers["X-Title"] == "Myrm Agent"
    assert result["custom_llm_provider"] == "openai"


def test_apply_wire_defaults_preserves_explicit_user_headers() -> None:
    existing_headers = {
        "HTTP-Referer": "https://custom.app",
        "X-Custom-Header": "foobar",
    }
    result = apply_wire_defaults(
        model="gpt-4o",
        model_kwargs={"extra_headers": existing_headers, "custom_llm_provider": "custom_openai"},
        wire_protocol="chat_completions",
        provider_id="vercel_ai_gateway",
    )
    headers = result.get("extra_headers")
    assert isinstance(headers, dict)
    assert headers["HTTP-Referer"] == "https://custom.app"
    assert headers["X-Custom-Header"] == "foobar"
    assert headers["X-Title"] == "Myrm Agent"
    assert result["custom_llm_provider"] == "custom_openai"


def test_apply_wire_defaults_untouched_for_other_providers() -> None:
    result = apply_wire_defaults(
        model="gpt-4o",
        model_kwargs={"temperature": 0.7},
        wire_protocol="chat_completions",
        provider_id="openai",
        base_url="https://api.openai.com/v1",
    )
    assert result == {"temperature": 0.7}
    assert "extra_headers" not in result


def test_enrich_model_config_vercel_ai_gateway() -> None:
    cfg = ModelConfig(
        model="openai/anthropic/claude-3-5-sonnet",
        api_key="vck_test_key",
        base_url="https://ai-gateway.vercel.sh/v1",
    )
    enriched = enrich_model_config(cfg, provider_id="vercel_ai_gateway")
    assert enriched.wire_protocol == "chat_completions"
    headers = enriched.model_kwargs.get("extra_headers")
    assert isinstance(headers, dict)
    assert headers["HTTP-Referer"] == "https://myrm.ai"
    assert headers["X-Title"] == "Myrm Agent"
    assert enriched.model_kwargs.get("custom_llm_provider") == "openai"


MINIMAX_URL = "https://api.minimaxi.com/v1"


@pytest.mark.parametrize("model", ["MiniMax-M3.1-Flash-Preview", "minimax/MiniMax-M3.1-Flash-Preview", "minimax-m3"])
def test_apply_wire_defaults_minimax_m3_gets_low_effort_on_minimax_hosts(model: str) -> None:
    result = apply_wire_defaults(model, {"temperature": 0.3}, "chat_completions", base_url=MINIMAX_URL)
    assert result == {"temperature": 0.3, "reasoning_effort": "low"}
    global_host = apply_wire_defaults(model, None, "chat_completions", base_url="https://api.minimax.io/v1")
    assert global_host == {"reasoning_effort": "low"}


@pytest.mark.parametrize(
    "stated",
    [
        {"reasoning_effort": "high"},
        {"extra_body": {"reasoning_effort": "medium"}},
        {"extra_body": {"reasoning": {"effort": "high"}}},
        {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 2048}}},
        {"extra_body": {"thinking": {"type": "disabled"}}},
    ],
)
def test_apply_wire_defaults_minimax_m3_keeps_the_reasoning_level_the_user_stated(stated: dict[str, object]) -> None:
    result = apply_wire_defaults("MiniMax-M3.1-Flash-Preview", stated, "chat_completions", base_url=MINIMAX_URL)
    assert result == stated


@pytest.mark.parametrize(
    ("model", "wire", "base_url"),
    [
        ("MiniMax-M3.1-Flash-Preview", "chat_completions", "https://openrouter.ai/api/v1"),
        ("MiniMax-M3.1-Flash-Preview", "chat_completions", None),
        ("MiniMax-M3.1-Flash-Preview", "anthropic_messages", MINIMAX_URL),
        ("MiniMax-M2.7", "chat_completions", MINIMAX_URL),
        ("deepseek-v4.1-flash", "chat_completions", MINIMAX_URL),
    ],
)
def test_apply_wire_defaults_minimax_effort_is_scoped_to_m3_on_minimax_hosts(model: str, wire: str, base_url: str | None) -> None:
    assert apply_wire_defaults(model, None, wire, base_url=base_url) == {}


def test_enrich_model_config_minimax_m3_plan_endpoint() -> None:
    cfg = ModelConfig(model="minimax/MiniMax-M3.1-Flash-Preview", api_key="sk-cp-test", base_url=MINIMAX_URL)
    enriched = enrich_model_config(cfg)
    assert enriched.wire_protocol == "chat_completions"
    assert enriched.model_kwargs == {"reasoning_effort": "low"}
