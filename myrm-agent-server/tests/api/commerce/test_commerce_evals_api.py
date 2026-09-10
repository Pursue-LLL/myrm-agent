"""Integration tests for Commerce State-Slice Evaluation API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.commerce.evals import router as commerce_evals_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(commerce_evals_router, prefix="/api/v1")
    return TestClient(app)


class TestCommerceEvalsApi:
    def test_get_presets(self, client: TestClient) -> None:
        response = client.get("/api/v1/commerce/evals/presets")
        assert response.status_code == 200
        payload = response.json()
        assert payload["code"] in (0, 200)
        cases = payload["data"]
        assert len(cases) >= 4
        case_ids = {c["case_id"] for c in cases}
        assert "slice_ret_01_variant_stock_converge" in case_ids
        assert "slice_ret_02_cart_capacity_guard" in case_ids
        assert "slice_merch_03_price_staged_guardrail" in case_ids
        assert "slice_trv_04_policy_inquiry" in case_ids

    def test_generate_slice_variant_resolution(self, client: TestClient) -> None:
        req = {
            "name": "Custom Variant Resolution Test",
            "domain": "retail",
            "role": "storefront",
            "user_prompt": "I want running shoes size 42",
            "scenario_preset": "variant_resolution_test",
        }
        response = client.post("/api/v1/commerce/evals/generate-slice", json=req)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["expected_action"] == "resolve_variant"
        assert data["domain"] == "retail"
        assert data["role"] == "storefront"
        assert data["target_product_id"] is not None

    def test_generate_slice_price_guardrail(self, client: TestClient) -> None:
        req = {
            "name": "Custom Price Drop Test",
            "domain": "retail",
            "role": "merchant",
            "user_prompt": "Drop price to 30",
            "scenario_preset": "price_staged_guardrail_test",
        }
        response = client.post("/api/v1/commerce/evals/generate-slice", json=req)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["expected_action"] == "price_guardrail_warn"
        assert data["role"] == "merchant"
        assert data["proposed_price"] == 40.0

    def test_run_slices_with_presets_succeeds(self, client: TestClient) -> None:
        presets_resp = client.get("/api/v1/commerce/evals/presets")
        assert presets_resp.status_code == 200
        cases = presets_resp.json()["data"]

        run_resp = client.post("/api/v1/commerce/evals/run-slices", json={"cases": cases})
        assert run_resp.status_code == 200
        res = run_resp.json()["data"]
        failed = [r for r in res["results"] if not r["passed"]]
        assert not failed, f"Failed cases: {failed}"
        assert res["total_cases"] == len(cases)
        assert res["passed_cases"] == len(cases)
        assert res["failed_cases"] == 0
        assert res["pass_rate"] == 1.0
        assert res["total_latency_ms"] >= 0.0

        for r in res["results"]:
            assert r["passed"] is True
            assert r["latency_ms"] >= 0.0

    def test_run_slices_empty_cases_rejected(self, client: TestClient) -> None:
        run_resp = client.post("/api/v1/commerce/evals/run-slices", json={"cases": []})
        assert run_resp.status_code == 400
        assert "No evaluation cases provided" in run_resp.json()["detail"]
