"""Unit tests for shared E2E provider-seed helpers."""

from __future__ import annotations

import pytest

from tests.support.e2e_provider_seed import (
    ResolvedE2ELlmEndpoints,
    resolve_e2e_llm_endpoints,
)
from tests.support.test_secrets import TestSecrets


def test_resolve_e2e_llm_endpoints_keeps_configured_urls_when_probe_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = TestSecrets(
        raw={
            "BASIC_API_KEY": "k-basic",
            "BASIC_BASE_URL": "http://localhost:20128/v1",
            "BASIC_MODEL": "openai-like/auto/best-coding",
            "LITE_API_KEY": "k-lite",
            "LITE_BASE_URL": "http://localhost:20128/v1",
            "LITE_MODEL": "openai-like/opencode-go/deepseek-v4-flash",
        }
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_openai_compatible_base",
        lambda _url, timeout_sec=3.0: True,
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_llm_api_key",
        lambda *_args, **_kwargs: True,
    )

    resolved = resolve_e2e_llm_endpoints(secrets)

    assert resolved == ResolvedE2ELlmEndpoints(
        basic_base_url="http://localhost:20128/v1",
        basic_model="openai-like/auto/best-coding",
        basic_api_key="k-basic",
        lite_base_url="http://localhost:20128/v1",
        lite_model="openai-like/opencode-go/deepseek-v4-flash",
        lite_api_key="k-lite",
        used_fallback=False,
    )


def test_resolve_e2e_llm_endpoints_falls_back_when_local_gateway_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = TestSecrets(
        raw={
            "BASIC_API_KEY": "k-basic",
            "BASIC_BASE_URL": "http://localhost:20128/v1",
            "BASIC_MODEL": "openai-like/auto/best-coding",
            "LITE_API_KEY": "k-lite",
            "LITE_BASE_URL": "http://localhost:20128/v1",
            "LITE_MODEL": "openai-like/opencode-go/deepseek-v4-flash",
            "E2E_DIRECT_OPENCODE_API_KEY": "k-direct",
        }
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_openai_compatible_base",
        lambda _url, timeout_sec=3.0: False,
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_llm_api_key",
        lambda *_args, **_kwargs: True,
    )

    resolved = resolve_e2e_llm_endpoints(secrets)

    assert resolved.used_fallback is True
    assert resolved.basic_base_url == "https://opencode.ai/zen/go/v1"
    assert resolved.lite_base_url == "https://opencode.ai/zen/go/v1"
    assert resolved.basic_model == "openai-like/deepseek-v4-flash"
    assert resolved.lite_model == "openai-like/deepseek-v4-flash"
    assert resolved.basic_api_key == "k-direct"
    assert resolved.lite_api_key == "k-direct"
