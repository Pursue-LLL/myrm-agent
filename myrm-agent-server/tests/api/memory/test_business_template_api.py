# [POS]: tests/api/memory/test_business_template_api.py
# [INPUT]: app.api.memory.business_template_router, FastAPI app
# [OUTPUT]: Integration API tests for BusinessScenarioExperienceTemplatesAndEscalationChecklistSuite (Item 107)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.business_template_router import (
    router as business_template_router,
)
from app.services.memory.business_template_service import (
    BusinessTemplateService,
    get_business_template_service,
)


@pytest.fixture
def isolated_service() -> BusinessTemplateService:
    """Provides an isolated in-memory BusinessTemplateService instance."""
    return BusinessTemplateService()


@pytest.fixture
def test_app(isolated_service: BusinessTemplateService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(business_template_router, prefix="/api/memory")
    app.dependency_overrides[get_business_template_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_list_and_search_business_templates_api(test_app: FastAPI) -> None:
    """Validate listing and searching templates via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List all templates
        res = await client.get("/api/memory/business-templates/list")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["total_count"] == 3
        template_ids = [t["template_id"] for t in data["templates"]]
        assert "BA-REV-01" in template_ids
        assert "RET-EXC-01" in template_ids
        assert "ESC-GATE-01" in template_ids

        # 2. Filter by category
        res_filtered = await client.get("/api/memory/business-templates/list?category=business_analysis")
        assert res_filtered.status_code == 200
        data_filtered = res_filtered.json()
        assert data_filtered["total_count"] == 1
        assert data_filtered["templates"][0]["template_id"] == "BA-REV-01"

        # 3. Search by keyword
        res_search = await client.get("/api/memory/business-templates/list?query=换货")
        assert res_search.status_code == 200
        data_search = res_search.json()
        assert data_search["total_count"] >= 1
        assert any(t["template_id"] == "RET-EXC-01" for t in data_search["templates"])


@pytest.mark.asyncio
async def test_evaluate_escalation_gate_api(test_app: FastAPI) -> None:
    """Validate evaluation of customer and operational contexts against escalation gates."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Case 1: Custom product order -> Escalate to human
        res1 = await client.post(
            "/api/memory/business-templates/evaluate-escalation",
            json={
                "order_id": "ORD-1001",
                "user_id": "USR-88",
                "intent": "换货要求更换定制签名版",
                "is_custom_order": True,
            },
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["action"] == "escalate_to_human"
        assert data1["reason"] == "policy_ambiguity"

        # Case 2: Out of stock -> Escalate to human
        res2 = await client.post(
            "/api/memory/business-templates/evaluate-escalation",
            json={
                "order_id": "ORD-1002",
                "intent": "更换为黑色L码",
                "inventory_available": False,
            },
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["action"] == "escalate_to_human"
        assert data2["reason"] == "inventory_shortage"

        # Case 3: Customer dispute count >= 2 -> Escalate to human
        res3 = await client.post(
            "/api/memory/business-templates/evaluate-escalation",
            json={
                "order_id": "ORD-1003",
                "intent": "不同意扣运费纠纷",
                "user_dispute_count": 2,
            },
        )
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["action"] == "escalate_to_human"
        assert data3["reason"] == "user_dispute_failed"

        # Case 4: Normal flow, user confirmed -> Automated proceed
        res4 = await client.post(
            "/api/memory/business-templates/evaluate-escalation",
            json={
                "order_id": "ORD-1004",
                "intent": "更换白色M码",
                "inventory_available": True,
                "warranty_valid": True,
                "user_confirmed": True,
            },
        )
        assert res4.status_code == 200
        data4 = res4.json()
        assert data4["action"] == "proceed_automated"
        assert data4["reason"] == "none"
        assert data4["suggested_skill_or_tool"] == "commit_retail_exchange"


@pytest.mark.asyncio
async def test_record_validation_feedback_api(test_app: FastAPI) -> None:
    """Validate continuous feedback recording and evolution metrics via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Feedback on existing template
        res = await client.post(
            "/api/memory/business-templates/validate",
            json={
                "template_id": "RET-EXC-01",
                "is_validated": True,
                "note": "Tau2 benchmark successful execution run",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["template_id"] == "RET-EXC-01"
        assert data["is_validated"] is True
        assert data["validated_count"] >= 29

        # Feedback on non-existing template -> 404
        res_404 = await client.post(
            "/api/memory/business-templates/validate",
            json={
                "template_id": "NOT-A-TEMPLATE",
                "is_validated": False,
            },
        )
        assert res_404.status_code == 404
