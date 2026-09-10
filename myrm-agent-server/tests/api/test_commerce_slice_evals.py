"""Tests for Commerce State-Slice Evaluation API endpoints.

Covers generate-slice and run-slices across multiple commerce scenarios and verticals.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.commerce.evals import router as evals_router

_test_app = FastAPI()
_test_app.include_router(evals_router, prefix="/api/v1/commerce/evals")


@pytest.mark.asyncio
async def test_generate_commerce_slice_variant_resolution() -> None:
    """Test generating a variant resolution slice evaluation case."""
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/commerce/evals/generate-slice",
            json={
                "name": "Test Variant Slice",
                "domain": "retail",
                "role": "storefront",
                "user_prompt": "I want running shoes size 42",
                "scenario_preset": "variant_resolution_test",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        case_data = data["data"]
        assert case_data["domain"] == "retail"
        assert case_data["expected_action"] == "resolve_variant"
        assert case_data["role"] == "storefront"


@pytest.mark.asyncio
async def test_generate_commerce_slice_price_guardrail() -> None:
    """Test generating a price change staged guardrail slice evaluation case."""
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/commerce/evals/generate-slice",
            json={
                "name": "Test Merchant Guardrail Slice",
                "domain": "travel",
                "role": "merchant",
                "user_prompt": "Drop room rate by 60%",
                "scenario_preset": "price_staged_guardrail_test",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        case_data = data["data"]
        assert case_data["domain"] == "travel"
        assert case_data["expected_action"] == "price_guardrail_warn"
        assert case_data["role"] == "merchant"


@pytest.mark.asyncio
async def test_run_commerce_slices_batch() -> None:
    """Test running a batch of commerce slices against vertical in-memory backends."""
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Generate two cases
        gen_resp1 = await client.post(
            "/api/v1/commerce/evals/generate-slice",
            json={
                "name": "Retail Variant Test",
                "domain": "retail",
                "role": "storefront",
                "user_prompt": "Blue color",
                "scenario_preset": "variant_resolution_test",
            },
        )
        case1 = gen_resp1.json()["data"]

        gen_resp2 = await client.post(
            "/api/v1/commerce/evals/generate-slice",
            json={
                "name": "Retail Cart Cap Test",
                "domain": "retail",
                "role": "storefront",
                "user_prompt": "Buy bulk",
                "scenario_preset": "cart_capacity_guard_test",
            },
        )
        case2 = gen_resp2.json()["data"]

        # 2. Run both slices
        run_resp = await client.post(
            "/api/v1/commerce/evals/run-slices",
            json={"cases": [case1, case2]},
        )
        assert run_resp.status_code == 200
        batch_data = run_resp.json()["data"]
        assert batch_data["total_cases"] == 2
        assert batch_data["passed_cases"] == 2
        assert batch_data["pass_rate"] == 1.0
        assert len(batch_data["results"]) == 2
        assert all(r["passed"] for r in batch_data["results"])
