"""Tests for Model Overrides and BYOK Context Pricing API.

[TEST TARGETS]
- app.api.config.model_overrides_router
- app.services.models.overrides.model_overrides_registry
- Hermes Agent v0.21.0 model_overrides parity
"""

from __future__ import annotations

from pathlib import Path
import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.config.model_overrides_router import model_overrides_router
from app.services.models.overrides.model_overrides_registry import (
    ModelOverridesRegistry,
)
from app.services.models.overrides.model_overrides_types import (
    Currency,
    ModelOverrideItem,
)

test_app = FastAPI()
test_app.include_router(model_overrides_router, prefix="/api/settings/model-overrides")


@pytest.fixture
async def overrides_client(tmp_path: pytest.TempPathFactory) -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=15.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_list_preloaded_skus(overrides_client: httpx.AsyncClient) -> None:
    """Verify modern 2026 baseline SKUs are preloaded."""
    response = await overrides_client.get("/api/settings/model-overrides/preloaded/skus")
    assert response.status_code == 200

    skus = response.json()
    assert isinstance(skus, list)
    assert len(skus) >= 5

    sku_ids = [s["model_id"] for s in skus]
    assert "glm-5.3-flash" in sku_ids
    assert "qwen-3.8-max" in sku_ids
    assert "gemini-3.7-flash" in sku_ids
    assert "deepseek-v3" in sku_ids


@pytest.mark.asyncio
async def test_upsert_and_get_model_override(
    overrides_client: httpx.AsyncClient,
) -> None:
    """Verify creating and retrieving custom context window and pricing override."""
    model_id = "test-glm-5.3-custom"
    payload = {
        "custom_context_window": 1_000_000,
        "custom_max_output_tokens": 16_384,
        "input_cost_per_mtoken": 0.08,
        "output_cost_per_mtoken": 0.12,
        "currency": "USD",
        "enabled": True,
        "remarks": "OneAPI aggregator endpoint override",
    }

    put_res = await overrides_client.put(
        f"/api/settings/model-overrides/{model_id}",
        json=payload,
    )
    assert put_res.status_code == 200
    created = put_res.json()
    assert created["model_id"] == model_id
    assert created["custom_context_window"] == 1_000_000
    assert created["input_cost_per_mtoken"] == 0.08
    assert created["enabled"] is True

    get_res = await overrides_client.get(f"/api/settings/model-overrides/{model_id}")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["custom_context_window"] == 1_000_000
    assert retrieved["remarks"] == "OneAPI aggregator endpoint override"


@pytest.mark.asyncio
async def test_list_model_overrides(
    overrides_client: httpx.AsyncClient,
) -> None:
    """Verify listing all configured user model overrides."""
    model_id = "qwen-custom-override-list-test"
    await overrides_client.put(
        f"/api/settings/model-overrides/{model_id}",
        json={
            "custom_context_window": 500_000,
            "currency": "CNY",
            "enabled": True,
        },
    )

    list_res = await overrides_client.get("/api/settings/model-overrides")
    assert list_res.status_code == 200
    overrides = list_res.json()
    assert any(o["model_id"] == model_id for o in overrides)


@pytest.mark.asyncio
async def test_estimate_byok_cost(
    overrides_client: httpx.AsyncClient,
) -> None:
    """Verify BYOK real-time token cost estimation."""
    model_id = "cost-calc-model"
    # Set override: 10 USD per 1M input, 30 USD per 1M output
    await overrides_client.put(
        f"/api/settings/model-overrides/{model_id}",
        json={
            "input_cost_per_mtoken": 10.0,
            "output_cost_per_mtoken": 30.0,
            "currency": "USD",
            "enabled": True,
        },
    )

    calc_res = await overrides_client.post(
        "/api/settings/model-overrides/estimate-cost",
        json={
            "model_id": model_id,
            "input_tokens": 100_000,   # (100k / 1M) * 10 = 1.0 USD
            "output_tokens": 50_000,   # (50k / 1M) * 30 = 1.5 USD
        },
    )
    assert calc_res.status_code == 200
    data = calc_res.json()
    assert data["model_id"] == model_id
    assert data["input_cost"] == 1.0
    assert data["output_cost"] == 1.5
    assert data["total_cost"] == 2.5
    assert data["currency"] == "USD"
    assert data["is_overridden"] is True


@pytest.mark.asyncio
async def test_delete_model_override(
    overrides_client: httpx.AsyncClient,
) -> None:
    """Verify deleting a custom model override resets it."""
    model_id = "temp-to-delete-model"
    await overrides_client.put(
        f"/api/settings/model-overrides/{model_id}",
        json={"custom_context_window": 256_000},
    )

    del_res = await overrides_client.delete(f"/api/settings/model-overrides/{model_id}")
    assert del_res.status_code == 200

    get_res = await overrides_client.get(f"/api/settings/model-overrides/{model_id}")
    assert get_res.status_code == 404


def test_registry_resolution_logic(tmp_path: Path) -> None:
    """Unit test registry effective resolution mechanics."""
    test_file = tmp_path / "models" / "overrides.json"
    registry = ModelOverridesRegistry(persistence_file=test_file)

    # 1. Default fallback when unconfigured
    assert registry.resolve_effective_context_window("unknown-model", default_window=64_000) == 64_000

    # 2. Preloaded SKU fallback
    assert registry.resolve_effective_context_window("gemini-3.7-flash") == 1_048_576

    # 3. User override takes highest precedence
    registry.upsert_override(
        ModelOverrideItem(
            model_id="gemini-3.7-flash",
            custom_context_window=2_000_000,
            enabled=True,
            currency=Currency.USD,
        )
    )
    assert registry.resolve_effective_context_window("gemini-3.7-flash") == 2_000_000

    # 4. If disabled, fallback to preloaded
    disabled_override = registry.get_override("gemini-3.7-flash")
    assert disabled_override is not None
    disabled_override.enabled = False
    registry.upsert_override(disabled_override)
    assert registry.resolve_effective_context_window("gemini-3.7-flash") == 1_048_576
