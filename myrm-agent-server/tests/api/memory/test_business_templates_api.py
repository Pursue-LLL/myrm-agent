# [POS]: tests/api/memory/test_business_templates_api.py
# [INPUT]: app.api.memory.business_template_router, isolated FastAPI app
# [OUTPUT]: Integration API test suite for Business Experience Templates and Escalation Gate (Item 107)

"""API integration tests for Business Scenario Experience Templates Suite (Item 107)."""

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
def test_service() -> BusinessTemplateService:
    """Provides an isolated BusinessTemplateService instance."""
    return BusinessTemplateService()


@pytest.fixture
def test_app(test_service: BusinessTemplateService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(business_template_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_business_template_service] = lambda: test_service
    return app


@pytest.mark.asyncio
async def test_list_business_templates_default(test_app: FastAPI) -> None:
    """Verify listing seeded business templates returns standard industrial procedures."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/memory/business-templates/list")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total_count"] >= 3

        template_ids = {t["template_id"] for t in data["templates"]}
        assert "BA-REV-01" in template_ids
        assert "RET-EXC-01" in template_ids
        assert "ESC-GATE-01" in template_ids


@pytest.mark.asyncio
async def test_list_business_templates_with_category_and_query(test_app: FastAPI) -> None:
    """Verify category filtering and keyword search on templates list."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Category filter
        res_cat = await client.get("/api/v1/memory/business-templates/list?category=business_analysis")
        assert res_cat.status_code == 200
        cat_data = res_cat.json()
        assert cat_data["total_count"] >= 1
        for t in cat_data["templates"]:
            assert t["category"] == "business_analysis"

        # Search keyword
        res_search = await client.get("/api/v1/memory/business-templates/list?query=换货")
        assert res_search.status_code == 200
        search_data = res_search.json()
        assert search_data["total_count"] >= 1
        assert any("换货" in t["name"] or "换货" in t["summary"] for t in search_data["templates"])


@pytest.mark.asyncio
async def test_get_single_template(test_app: FastAPI) -> None:
    """Verify fetching individual template with checklist steps and 404 for unknown template."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_ok = await client.get("/api/v1/memory/business-templates/BA-REV-01")
        assert res_ok.status_code == 200
        tpl = res_ok.json()
        assert tpl["template_id"] == "BA-REV-01"
        assert len(tpl["checklist_steps"]) >= 3
        assert len(tpl["boundary_conditions"]) >= 1

        res_404 = await client.get("/api/v1/memory/business-templates/NON_EXISTENT_TPL")
        assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_evaluate_escalation_proceed(test_app: FastAPI) -> None:
    """Verify evaluate escalation gate allows automated flow when prerequisites pass."""
    payload = {
        "order_id": "ORD-12345",
        "user_id": "USR-67890",
        "intent": "exchange_size",
        "shipment_status": "delivered",
        "warranty_valid": True,
        "inventory_available": True,
        "user_dispute_count": 0,
        "is_custom_order": False,
        "policy_clear": True,
        "user_confirmed": True,
    }
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/memory/business-templates/evaluate-escalation", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "proceed_automated"
        assert data["reason"] == "none"
        assert data["suggested_skill_or_tool"] == "commit_retail_exchange"


@pytest.mark.asyncio
async def test_evaluate_escalation_triggers_human_for_policy_ambiguity(test_app: FastAPI) -> None:
    """Verify escalation gate intercepts ambiguous policy and routes to human specialist."""
    payload = {
        "order_id": "ORD-12346",
        "user_id": "USR-67891",
        "intent": "exchange_custom",
        "policy_clear": False,
    }
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/memory/business-templates/evaluate-escalation", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "escalate_to_human"
        assert data["reason"] == "policy_ambiguity"
        assert "route_to_human_specialist" in data["suggested_skill_or_tool"]


@pytest.mark.asyncio
async def test_evaluate_escalation_triggers_human_for_inventory_shortage(test_app: FastAPI) -> None:
    """Verify escalation gate intercepts stockout and routes to out-of-stock handler."""
    payload = {
        "order_id": "ORD-12347",
        "user_id": "USR-67892",
        "intent": "exchange_size",
        "inventory_available": False,
    }
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/memory/business-templates/evaluate-escalation", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "escalate_to_human"
        assert data["reason"] == "inventory_shortage"


@pytest.mark.asyncio
async def test_record_validation_feedback(test_app: FastAPI) -> None:
    """Verify recording execution feedback increments template confidence counters."""
    payload = {
        "template_id": "BA-REV-01",
        "is_validated": True,
        "note": "Audited Excel formula with data_only=True successfully",
    }
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/memory/business-templates/validate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["template_id"] == "BA-REV-01"
        assert data["is_validated"] is True
        assert data["validated_count"] >= 1


@pytest.mark.asyncio
async def test_export_procedure_memories_endpoint(test_app: FastAPI) -> None:
    """Verify exporting all templates as standard procedure memory items."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/memory/business-templates/export-procedure-memories")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total_count"] >= 3
        for item in data["items"]:
            assert item["entry_id"] != ""
            assert item["name"] != ""
            assert len(item["procedure_steps"]) > 0
            assert item["confidence"] == 1.0
