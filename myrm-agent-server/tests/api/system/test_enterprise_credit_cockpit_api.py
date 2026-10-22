"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.enterprise_credit_cockpit_api::router

[OUTPUT]:
- Pytest verification for enterprise credit ops cockpit endpoints, quota configuration, and unified audit trails.

[POS]:
tests/api/system/test_enterprise_credit_cockpit_api.py — 企业用量与风险运营驾驶舱 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.enterprise_credit_cockpit_api import router as enterprise_credit_router

test_app = FastAPI()
test_app.include_router(enterprise_credit_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_enterprise_credit_cockpit_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset ledger
    reset_resp = await async_client.post("/api/v1/system/enterprise-credit/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Configure enterprise quota
    cfg_resp = await async_client.post(
        "/api/v1/system/enterprise-credit/configure-quota",
        json={"total_quota": 2000.0, "warning_threshold_pct": 85.0},
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json() == {"ok": True}

    # 3. Check clean cockpit status
    cockpit_resp = await async_client.get("/api/v1/system/enterprise-credit/cockpit")
    assert cockpit_resp.status_code == 200
    cockpit_data = cockpit_resp.json()
    assert cockpit_data["total_credit_quota"] == 2000.0
    assert cockpit_data["total_credit_spent"] == 0.0
    assert cockpit_data["available_credit"] == 2000.0
    assert cockpit_data["warning_threshold_pct"] == 85.0
    assert cockpit_data["is_quota_breached"] is False
    assert cockpit_data["risk_event_count"] == 0
    assert cockpit_data["blocked_count"] == 0

    # 4. Record normal business transaction
    tx1_resp = await async_client.post(
        "/api/v1/system/enterprise-credit/record",
        json={
            "actor_id": "emp_sarah",
            "product_surface": "webui",
            "interaction_summary": "Quarterly financial summary generation",
            "data_object_scope": "finance.statements",
            "credit_consumed": 35.0,
            "risk_level": "NONE",
            "risk_behavior": "NONE",
            "policy_verdict": "ALLOW",
        },
    )
    assert tx1_resp.status_code == 200
    tx1_data = tx1_resp.json()
    assert tx1_data["actor_id"] == "emp_sarah"
    assert tx1_data["credit_consumed"] == 35.0
    assert tx1_data["policy_verdict"] == "ALLOW"

    # 5. Record blocked critical risk transaction
    tx2_resp = await async_client.post(
        "/api/v1/system/enterprise-credit/record",
        json={
            "actor_id": "emp_david",
            "product_surface": "desktop",
            "interaction_summary": "Attempted unauthorized dump of customer leads",
            "data_object_scope": "crm.customer_leads",
            "credit_consumed": 75.0,
            "risk_level": "CRITICAL",
            "risk_behavior": "SENSITIVE_DATA_EXPORT",
            "policy_verdict": "BLOCKED",
        },
    )
    assert tx2_resp.status_code == 200
    tx2_data = tx2_resp.json()
    assert tx2_data["actor_id"] == "emp_david"
    assert tx2_data["risk_level"] == "CRITICAL"
    assert tx2_data["policy_verdict"] == "BLOCKED"

    # 6. Verify cockpit snapshot aggregates
    updated_cockpit = await async_client.get("/api/v1/system/enterprise-credit/cockpit")
    assert updated_cockpit.status_code == 200
    updated_data = updated_cockpit.json()
    assert updated_data["total_credit_spent"] == 110.0
    assert updated_data["available_credit"] == 1890.0
    assert updated_data["total_audit_records"] == 2
    assert updated_data["risk_event_count"] == 1
    assert updated_data["blocked_count"] == 1
    assert len(updated_data["recent_audit_records"]) == 2

    # 7. Query audit trail by risk level
    audit_risk = await async_client.get("/api/v1/system/enterprise-credit/audit-trail?risk_level=CRITICAL")
    assert audit_risk.status_code == 200
    risk_data = audit_risk.json()
    assert risk_data["total_matched"] == 1
    assert risk_data["records"][0]["actor_id"] == "emp_david"
    assert risk_data["records"][0]["data_object_scope"] == "crm.customer_leads"

    # 8. Query audit trail by actor
    audit_actor = await async_client.get("/api/v1/system/enterprise-credit/audit-trail?actor_id=emp_sarah")
    assert audit_actor.status_code == 200
    actor_data = audit_actor.json()
    assert actor_data["total_matched"] == 1
    assert actor_data["records"][0]["product_surface"] == "webui"
