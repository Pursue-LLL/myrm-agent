"""Unit tests for shared E2E provider-seed helpers."""

from __future__ import annotations

import pytest

from tests.support.e2e_provider_seed import (
    ResolvedE2ELlmEndpoints,
    _chat_probe_max_tokens,
    _chat_probe_model,
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
    )


def test_resolve_e2e_llm_endpoints_raises_when_local_gateway_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = TestSecrets(
        raw={
            "BASIC_API_KEY": "k-basic",
            "BASIC_BASE_URL": "http://localhost:20128/v1",
            "BASIC_MODEL": "openai-like/auto/best-coding",
        }
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_openai_compatible_base",
        lambda _url, timeout_sec=3.0: False,
    )

    with pytest.raises(RuntimeError, match="unreachable"):
        resolve_e2e_llm_endpoints(secrets)


def test_resolve_e2e_llm_endpoints_raises_when_gateway_key_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = TestSecrets(
        raw={
            "BASIC_API_KEY": "k-basic",
            "BASIC_BASE_URL": "http://localhost:20128/v1",
            "BASIC_MODEL": "openai-like/agnes-2.5-flash",
        }
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_openai_compatible_base",
        lambda _url, timeout_sec=3.0: True,
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_llm_api_key",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(RuntimeError, match="rejected BASIC_API_KEY"):
        resolve_e2e_llm_endpoints(secrets)


def test_resolve_e2e_llm_endpoints_raises_when_direct_endpoint_model_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = TestSecrets(
        raw={
            "BASIC_API_KEY": "k-basic",
            "BASIC_BASE_URL": "https://opencode.ai/zen/go/v1",
            "BASIC_MODEL": "openai-like/ox-alpha-free",
        }
    )
    monkeypatch.setattr(
        "tests.support.e2e_provider_seed.probe_llm_api_key",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(RuntimeError, match="BASIC_MODEL chat preflight failed"):
        resolve_e2e_llm_endpoints(secrets)


def test_chat_probe_model_preserves_combo_pattern_for_local_gateway() -> None:
    assert (
        _chat_probe_model(
            "http://localhost:20128/v1",
            "openai-like/agnes-2.5-flash",
        )
        == "openai-like/agnes-2.5-flash"
    )
    assert (
        _chat_probe_model(
            "https://apihub.agnes-ai.com/v1",
            "openai-like/agnes-2.5-flash",
        )
        == "agnes-2.5-flash"
    )
    assert _chat_probe_max_tokens("http://localhost:20128/v1") == 16
    assert _chat_probe_max_tokens("https://api.minimaxi.com/v1") == 1


def test_probe_llm_api_key_once_injects_opencode_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support.e2e_provider_seed import _probe_llm_api_key_once
    import urllib.request

    captured_headers: dict[str, str] = {}

    class DummyResponse:
        status = 200

        def __enter__(self) -> DummyResponse:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def dummy_urlopen(req: urllib.request.Request, **_kwargs: object) -> DummyResponse:
        nonlocal captured_headers
        captured_headers = dict(req.headers)
        return DummyResponse()

    monkeypatch.setattr(urllib.request, "urlopen", dummy_urlopen)

    ok = _probe_llm_api_key_once(
        base_url="https://opencode.ai/zen/go/v1",
        api_key="sk-test",
        model="openai-like/deepseek-v4-flash",
    )
    assert ok is True
    # Header keys in Request.headers may be case-folded or title-cased
    headers_lower = {k.lower(): v for k, v in captured_headers.items()}
    assert headers_lower.get("x-opencode-session") == "e2e-preflight-session"
    assert headers_lower.get("user-agent") == "Myrm-E2E/1.0"

