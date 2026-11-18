"""Unit tests for wire defaults and Vercel AI Gateway attribution headers."""

from __future__ import annotations

import httpx
from myrm_agent_harness.api.hooks import vercel_headers
from myrm_agent_harness.toolkits.llms.core.attribution import openrouter_headers

from app.core.brand import CLIENT_ATTRIBUTION
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
    assert headers == vercel_headers(CLIENT_ATTRIBUTION)
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
    assert headers["HTTP-Referer"] == CLIENT_ATTRIBUTION.site_url
    assert headers["X-Title"] == CLIENT_ATTRIBUTION.app_name
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
    assert headers["X-Title"] == CLIENT_ATTRIBUTION.app_name
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
    assert enriched.model_kwargs is not None
    headers = enriched.model_kwargs.get("extra_headers")
    assert isinstance(headers, dict)
    assert headers["HTTP-Referer"] == CLIENT_ATTRIBUTION.site_url
    assert headers["X-Title"] == CLIENT_ATTRIBUTION.app_name
    assert enriched.model_kwargs.get("custom_llm_provider") == "openai"


def test_the_servers_identity_builds_a_request_for_each_gateway() -> None:
    """httpx refuses a header value it cannot encode while building the request, so each set must construct one."""
    for headers in (vercel_headers(CLIENT_ATTRIBUTION), openrouter_headers(CLIENT_ATTRIBUTION)):
        request = httpx.Request("POST", "https://gateway.example/v1/chat/completions", headers=headers)
        assert request.headers["HTTP-Referer"] == CLIENT_ATTRIBUTION.site_url
