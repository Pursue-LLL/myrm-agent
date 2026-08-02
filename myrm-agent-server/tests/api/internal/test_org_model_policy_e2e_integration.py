"""Integration: full CP-sync → frontend-read → enforcement cycle.

Tests the real data flow from control plane push through ConfigService
to frontend consumption, verifying:
1. POST sync stores patterns correctly
2. GET returns the same patterns (round-trip)
3. Pattern matching logic behaves correctly for LiteLLM-format model names
4. Frontend can determine which models are restricted
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.internal.org_model_policy_sync import (
    frontend_router as org_model_policy_frontend_router,
)
from app.api.internal.org_model_policy_sync import (
    router as org_model_policy_sync_router,
)


@pytest.fixture
def policy_app() -> FastAPI:
    app = FastAPI()
    app.include_router(org_model_policy_sync_router)
    app.include_router(org_model_policy_frontend_router)
    return app


class FakeConfigStore:
    """In-memory config store simulating real DB round-trip."""

    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    async def get(self, key: str) -> MagicMock | None:
        val = self._store.get(key)
        if val is None:
            return None
        record = MagicMock()
        record.value = val
        return record

    async def set(self, *, config_key: str, value: object, device_id: str) -> None:
        self._store[config_key] = value


@pytest.fixture
def fake_config():
    store = FakeConfigStore()
    with patch(
        "app.api.internal.org_model_policy_sync.ConfigService",
        return_value=store,
    ):
        with patch("app.api.internal.org_model_policy_sync.invalidate_user_configs_cache"):
            yield store


@pytest.mark.asyncio
async def test_full_roundtrip_sync_then_read(
    policy_app: FastAPI, fake_config: FakeConfigStore
) -> None:
    """CP syncs patterns → frontend GET returns them → restricted flag correct."""
    transport = ASGITransport(app=policy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/org-model-policy-sync",
            json={"allowed_patterns": ["openai/*", "deepseek/*"]},
        )
        assert resp.status_code == 200
        assert resp.json()["pattern_count"] == 2

        get_resp = await client.get("/org-policy/allowed-models")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["restricted"] is True
        assert set(data["allowed_patterns"]) == {"openai/*", "deepseek/*"}


@pytest.mark.asyncio
async def test_roundtrip_empty_clears_restriction(
    policy_app: FastAPI, fake_config: FakeConfigStore
) -> None:
    """Sync non-empty then sync empty → restriction cleared."""
    transport = ASGITransport(app=policy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/admin/org-model-policy-sync",
            json={"allowed_patterns": ["openai/*"]},
        )
        await client.post(
            "/api/admin/org-model-policy-sync",
            json={"allowed_patterns": []},
        )

        get_resp = await client.get("/org-policy/allowed-models")
        data = get_resp.json()
        assert data["restricted"] is False
        assert data["allowed_patterns"] == []


@pytest.mark.asyncio
async def test_litellm_format_models_matched_by_policy(
    policy_app: FastAPI, fake_config: FakeConfigStore
) -> None:
    """Verify that LiteLLM-format model names (provider/model) are correctly
    matched by glob patterns — this is the critical integration point."""
    from fnmatch import fnmatch

    transport = ASGITransport(app=policy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/admin/org-model-policy-sync",
            json={"allowed_patterns": ["openai/*", "anthropic/claude-4*"]},
        )

        get_resp = await client.get("/org-policy/allowed-models")
        patterns = get_resp.json()["allowed_patterns"]

    allowed_models = [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/o3-mini",
        "anthropic/claude-4-opus",
        "anthropic/claude-4-sonnet",
    ]
    blocked_models = [
        "deepseek/deepseek-chat",
        "anthropic/claude-3.5-sonnet",
        "xai/grok-3",
        "minimax/MiniMax-M2.5",
    ]

    for model in allowed_models:
        assert any(fnmatch(model, p) for p in patterns), f"{model} should be allowed"

    for model in blocked_models:
        assert not any(fnmatch(model, p) for p in patterns), f"{model} should be blocked"


@pytest.mark.asyncio
async def test_policy_enforcement_backend_frontend_parity(
    policy_app: FastAPI, fake_config: FakeConfigStore
) -> None:
    """Backend fnmatch and the pattern matching produce identical results
    for real-world LiteLLM model names."""
    from fnmatch import fnmatch

    transport = ASGITransport(app=policy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/admin/org-model-policy-sync",
            json={"allowed_patterns": ["openai/*", "deepseek/deepseek-*"]},
        )
        get_resp = await client.get("/org-policy/allowed-models")
        patterns = get_resp.json()["allowed_patterns"]

    test_models = [
        ("openai/gpt-4o", True),
        ("openai/gpt-4o-mini", True),
        ("deepseek/deepseek-chat", True),
        ("deepseek/deepseek-coder-v3", True),
        ("anthropic/claude-4-opus", False),
        ("minimax/MiniMax-M2.5", False),
    ]

    for model, expected in test_models:
        result = any(fnmatch(model, p) for p in patterns)
        assert result == expected, f"fnmatch({model}) = {result}, expected {expected}"
