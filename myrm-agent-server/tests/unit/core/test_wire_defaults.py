"""Unit tests for wire defaults and Vercel AI Gateway attribution headers."""

from __future__ import annotations

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
