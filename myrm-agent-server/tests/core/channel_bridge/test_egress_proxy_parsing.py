"""Tests for egress proxy configuration parsing and propagation."""

from __future__ import annotations

import pytest

from app.core.channel_bridge.config_parsers import _build_enriched_model_config
from app.core.types import ModelConfig
from app.services.agent.params.models import ModelSelection
from app.services.agent.params.resolvers import _resolve_model_config


def test_model_config_egress_proxy_normalization() -> None:
    """Test that ModelConfig normalizes whitespace and trailing slashes for egress_proxy."""
    cfg = ModelConfig(
        model="gpt-4o",
        api_key="sk-test",
        egress_proxy="  http://127.0.0.1:7890/  ",
    )
    assert cfg.egress_proxy == "http://127.0.0.1:7890"

    cfg_empty = ModelConfig(
        model="gpt-4o",
        api_key="sk-test",
        egress_proxy="   ",
    )
    assert cfg_empty.egress_proxy is None


def test_model_config_camel_case_alias() -> None:
    """Test that ModelConfig accepts egressProxy camelCase key from JSON."""
    data = {
        "model": "gpt-4o",
        "apiKey": "sk-test",
        "egressProxy": "socks5://127.0.0.1:1080",
    }
    cfg = ModelConfig.model_validate(data)
    assert cfg.egress_proxy == "socks5://127.0.0.1:1080"


def test_build_enriched_model_config_with_egress_proxy() -> None:
    """Test that _build_enriched_model_config extracts egressProxy from provider."""
    provider = {
        "id": "openai",
        "apiKey": "sk-openai-key",
        "egressProxy": "http://proxy.corp.internal:8080",
    }
    cfg = _build_enriched_model_config(
        provider_id="openai",
        model="gpt-4o",
        provider=provider,
        providers_dict=None,
    )
    assert cfg is not None
    assert cfg.egress_proxy == "http://proxy.corp.internal:8080"


@pytest.mark.asyncio
async def test_resolve_model_config_with_egress_proxy() -> None:
    """Test that _resolve_model_config extracts egressProxy from provider dictionary."""
    selection = ModelSelection(
        provider_id="custom_prov",
        model="deepseek-chat",
    )
    providers_dict = {
        "providers": [
            {
                "id": "custom_prov",
                "isEnabled": True,
                "apiKey": "sk-custom",
                "apiUrl": "https://api.custom.com/v1",
                "egressProxy": "socks5://10.0.0.2:1080",
            }
        ]
    }
    cfg = await _resolve_model_config(selection, providers_dict)
    assert cfg.egress_proxy == "socks5://10.0.0.2:1080"
