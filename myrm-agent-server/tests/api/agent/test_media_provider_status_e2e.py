"""Live E2E for GET /api/v1/agents/media-provider-status (MediaCredentialInline backend)."""

from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080")

_skip_e2e = pytest.mark.skipif(
    not os.getenv("RUN_E2E_TESTS"),
    reason="Set RUN_E2E_TESTS=1 to run end-to-end tests against live server",
)


@_skip_e2e
def test_media_provider_status_returns_provider_map() -> None:
    resp = httpx.get(f"{BASE_URL}/api/v1/agents/media-provider-status", timeout=15.0)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("success") is True
    providers = body.get("data", {}).get("providers")
    assert isinstance(providers, dict)
    assert len(providers) >= 1
    for pid, info in providers.items():
        assert isinstance(pid, str)
        assert isinstance(info, dict)
        assert "hasApiKey" in info
        assert "healthy" in info
        assert "configured" in info
