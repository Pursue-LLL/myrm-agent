"""Tests for Commerce Prebuilt Agent Templates & Category Discovery.

[INPUT]
- fastapi::testclient::TestClient
- app.api.agents.templates::list_templates

[OUTPUT]
- Verifies that storefront_shopper_agent and backoffice_merchant_agent templates are correctly exposed.
"""

from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient


def test_commerce_templates_discovered(client: TestClient):
    """Verify storefront_shopper_agent and backoffice_merchant_agent are discoverable."""
    response = client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    templates = data["data"]
    template_ids = [t["id"] for t in templates]

    assert "storefront_shopper_agent" in template_ids
    assert "backoffice_merchant_agent" in template_ids

    shopper = next(t for t in templates if t["id"] == "storefront_shopper_agent")
    assert shopper["category"] == "commerce"
    assert shopper["agent_type"] == "individual"
    assert shopper["avatar_url"] == "lucide:shopping-bag"
    assert "Storefront" in shopper["name"] or "导购" in shopper["name"]

    merchant = next(t for t in templates if t["id"] == "backoffice_merchant_agent")
    assert merchant["category"] == "commerce"
    assert merchant["agent_type"] == "individual"
    assert merchant["avatar_url"] == "lucide:store"
    assert "Merchant" in merchant["name"] or "经营" in merchant["name"]


def test_commerce_templates_i18n_zh(client: TestClient):
    """Verify Chinese localization for commerce templates when Accept-Language: zh."""
    response = client.get("/api/v1/agents/templates", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    assert response.status_code == 200
    templates = response.json()["data"]

    shopper = next(t for t in templates if t["id"] == "storefront_shopper_agent")
    assert "智能导购" in shopper["name"]
    assert "导购" in shopper["description"]

    merchant = next(t for t in templates if t["id"] == "backoffice_merchant_agent")
    assert "店铺经营参谋" in merchant["name"]
    assert "经营参谋" in merchant["description"]


def test_commerce_templates_instantiation(client: TestClient):
    """Verify instantiating storefront_shopper_agent creates the agent properly."""
    with patch(
        "app.api.agents.templates._ensure_skills_enabled",
        new_callable=AsyncMock,
    ):
        response = client.post(
            "/api/v1/agents/instantiate-template/storefront_shopper_agent",
            headers={"Accept-Language": "zh-CN"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        agent_data = result["data"]
        assert "智能导购" in agent_data["name"]
        assert agent_data["personality_style"] in ("friendly", "professional")
