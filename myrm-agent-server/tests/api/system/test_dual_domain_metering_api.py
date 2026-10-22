"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.dual_domain_metering_api::router

[OUTPUT]:
- Pytest verification for dual-domain metering boundary and 3D penetrating cost attribution REST endpoints.

[POS]:
tests/api/system/test_dual_domain_metering_api.py — 双域透明计量边界与三维穿透成本核算 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.dual_domain_metering_api import router as ddm_router

test_app = FastAPI()
test_app.include_router(ddm_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_dual_domain_metering_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset ledger
    reset_resp = await async_client.post("/api/v1/system/dual-domain-metering/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initially empty summary
    init_sum = await async_client.get("/api/v1/system/dual-domain-metering/summary/sess-enterprise-99")
    assert init_sum.status_code == 200
    assert init_sum.json()["total_operations"] == 0
    assert init_sum.json()["total_cost_usd"] == 0.0

    # 3. Ingest Gateway Domain Record (Model Token)
    r1_resp = await async_client.post(
        "/api/v1/system/dual-domain-metering/record",
        json={
            "session_id": "sess-enterprise-99",
            "domain": "gateway_domain",
            "operation_name": "llm_chat_completion",
            "resource_units": 4000.0,
            "cost_breakdown": {
                "model_token_cost_usd": 0.012,
                "sandbox_compute_cost_usd": 0.0,
                "thirdparty_tool_cost_usd": 0.0,
                "total_cost_usd": 0.012,
            },
            "billable": True,
            "policy_note": "Gateway Ingress/Egress Prompt Token",
        },
    )
    assert r1_resp.status_code == 200
    r1_data = r1_resp.json()
    assert r1_data["domain"] == "gateway_domain"
    assert r1_data["cost_breakdown"]["model_token_cost_usd"] == 0.012

    # 4. Ingest Sandbox Domain Record (Compute CPU/RAM)
    r2_resp = await async_client.post(
        "/api/v1/system/dual-domain-metering/record",
        json={
            "session_id": "sess-enterprise-99",
            "domain": "sandbox_domain",
            "operation_name": "python_pandas_analysis",
            "resource_units": 15.0,  # 15s compute
            "cost_breakdown": {
                "model_token_cost_usd": 0.0,
                "sandbox_compute_cost_usd": 0.003,
                "thirdparty_tool_cost_usd": 0.0,
                "total_cost_usd": 0.003,
            },
            "billable": True,
            "policy_note": "Isolated Container CPU/RAM Compute",
        },
    )
    assert r2_resp.status_code == 200
    r2_data = r2_resp.json()
    assert r2_data["domain"] == "sandbox_domain"
    assert r2_data["cost_breakdown"]["sandbox_compute_cost_usd"] == 0.003

    # 5. Ingest Third-Party Tool Call Record
    r3_resp = await async_client.post(
        "/api/v1/system/dual-domain-metering/record",
        json={
            "session_id": "sess-enterprise-99",
            "domain": "sandbox_domain",
            "operation_name": "paid_external_web_search",
            "resource_units": 1.0,
            "cost_breakdown": {
                "model_token_cost_usd": 0.0,
                "sandbox_compute_cost_usd": 0.0,
                "thirdparty_tool_cost_usd": 0.005,
                "total_cost_usd": 0.005,
            },
            "billable": True,
            "policy_note": "External Search API Surcharge",
        },
    )
    assert r3_resp.status_code == 200

    # 6. Check Aggregated Session Summary
    sum_resp = await async_client.get("/api/v1/system/dual-domain-metering/summary/sess-enterprise-99")
    assert sum_resp.status_code == 200
    sum_data = sum_resp.json()
    assert sum_data["total_operations"] == 3
    assert sum_data["gateway_ops_count"] == 1
    assert sum_data["sandbox_ops_count"] == 2
    assert sum_data["gateway_token_cost_usd"] == pytest.approx(0.012)
    assert sum_data["sandbox_compute_cost_usd"] == pytest.approx(0.003)
    assert sum_data["thirdparty_tool_cost_usd"] == pytest.approx(0.005)
    assert sum_data["total_cost_usd"] == pytest.approx(0.02)
    assert sum_data["gateway_cost_ratio"] == pytest.approx(0.6)  # 0.012 / 0.02 = 0.6
    assert sum_data["sandbox_cost_ratio"] == pytest.approx(0.4)  # (0.003 + 0.005) / 0.02 = 0.4

    # 7. Generate Tamper-Proof Statement
    stmt_resp = await async_client.post("/api/v1/system/dual-domain-metering/statement/sess-enterprise-99")
    assert stmt_resp.status_code == 200
    stmt_data = stmt_resp.json()
    assert stmt_data["session_id"] == "sess-enterprise-99"
    assert len(stmt_data["records"]) == 3
    assert len(stmt_data["integrity_sha256"]) == 64

    # 8. List statements
    stmts_resp = await async_client.get("/api/v1/system/dual-domain-metering/statements")
    assert stmts_resp.status_code == 200
    assert len(stmts_resp.json()) == 1

    # 9. Invalid domain rejected with 400
    bad_resp = await async_client.post(
        "/api/v1/system/dual-domain-metering/record",
        json={
            "session_id": "sess-test",
            "domain": "invalid_domain_type",
            "operation_name": "op",
            "resource_units": 1.0,
            "cost_breakdown": {
                "model_token_cost_usd": 0.0,
                "sandbox_compute_cost_usd": 0.0,
                "thirdparty_tool_cost_usd": 0.0,
                "total_cost_usd": 0.0,
            },
        },
    )
    assert bad_resp.status_code == 400
