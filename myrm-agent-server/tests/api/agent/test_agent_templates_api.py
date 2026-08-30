from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.testclient import TestClient


def test_list_templates(client: TestClient):
    """Test listing agent templates."""
    response = client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    templates = data["data"]
    assert isinstance(templates, list)

    if len(templates) > 0:
        first = templates[0]
        assert "id" in first
        assert "name" in first
        assert "agent_type" in first


def test_instantiate_template_not_found(client: TestClient):
    """Test instantiating a non-existent template."""
    response = client.post("/api/v1/agents/instantiate-template/non_existent_template_123")
    assert response.status_code == 404


def test_list_templates_includes_team_type(client: TestClient):
    """Team templates expose members metadata for Template Market UI."""
    response = client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    templates = response.json()["data"]
    team_templates = [t for t in templates if t.get("agent_type") == "team"]
    assert team_templates, "expected at least one team template seed"
    first_team = team_templates[0]
    assert first_team.get("members")
    assert len(first_team["members"]) >= 1


def test_official_document_assistant_template_loaded(client: TestClient):
    """official_document_assistant.yaml is discoverable via templates API."""
    response = client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    templates = response.json()["data"]
    ids = [t["id"] for t in templates]
    assert "official_document_assistant" in ids

    tpl = next(t for t in templates if t["id"] == "official_document_assistant")
    assert tpl["agent_type"] == "individual"
    assert "公文" in tpl["name"] or "Official" in tpl["name"]


def test_official_document_assistant_instantiate(client: TestClient):
    """Instantiating official_document_assistant creates an agent with correct fields."""
    with patch(
        "app.api.agents.templates._ensure_skills_enabled",
        new_callable=AsyncMock,
    ):
        response = client.post("/api/v1/agents/instantiate-template/official_document_assistant")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    agent = data["data"]
    assert "GB/T 9704" in agent.get("description", "")
    assert agent["agent_type"] == "individual"
    assert "office-document" in agent.get("skill_ids", [])


def test_official_document_assistant_i18n_zh(client: TestClient):
    """Accept-Language: zh returns Chinese name and description."""
    response = client.get("/api/v1/agents/templates", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    assert response.status_code == 200
    templates = response.json()["data"]
    tpl = next(t for t in templates if t["id"] == "official_document_assistant")
    assert "公文" in tpl["name"]
    assert "GB/T 9704" in tpl.get("description", "")


def test_official_document_assistant_i18n_en(client: TestClient):
    """Accept-Language: en returns English name and description."""
    response = client.get("/api/v1/agents/templates", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert response.status_code == 200
    templates = response.json()["data"]
    tpl = next(t for t in templates if t["id"] == "official_document_assistant")
    assert "Official" in tpl["name"]
    assert "GB/T 9704" in tpl.get("description", "")


def test_official_document_assistant_instantiate_missing_skill(client: TestClient):
    """Instantiation fails gracefully when required skill is not in the system."""

    with patch(
        "app.api.agents.templates._ensure_skills_enabled",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=400, detail="Skill 'office-document' does not exist"),
    ):
        response = client.post("/api/v1/agents/instantiate-template/official_document_assistant")

    assert response.status_code == 400
    assert "office-document" in response.json()["detail"]


def test_pareto_presets_templates_api(client: TestClient):
    """Pareto preset templates are discoverable with correct Pareto metadata."""
    response = client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    templates = response.json()["data"]
    pareto_tpls = [t for t in templates if t.get("is_pareto_preset")]
    assert len(pareto_tpls) >= 3

    ids = {t["id"] for t in pareto_tpls}
    assert "pareto_deep_researcher" in ids
    assert "pareto_code_craftsman" in ids
    assert "pareto_balanced_squad" in ids

    # Check Deep Researcher metadata
    dr = next(t for t in pareto_tpls if t["id"] == "pareto_deep_researcher")
    assert dr["cost_reduction_ratio"] == 0.70
    assert dr["agent_type"] == "individual"
    assert dr.get("routing_config") is not None
    assert dr.get("moa_overlay") is not None
    assert dr["moa_overlay"]["enabled"] is True

    # Check Balanced Squad team metadata
    bs = next(t for t in pareto_tpls if t["id"] == "pareto_balanced_squad")
    assert bs["cost_reduction_ratio"] == 0.75
    assert bs["agent_type"] == "team"
    assert bs.get("members") is not None
    assert len(bs["members"]) >= 2


def test_pareto_presets_instantiate(client: TestClient):
    """Instantiating a Pareto preset persists routing_config and moa_overlay."""
    response = client.post("/api/v1/agents/instantiate-template/pareto_deep_researcher")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    agent = data["data"]
    assert agent["is_pareto_preset"] is True
    assert agent["cost_reduction_ratio"] == 0.70
    assert agent["model_selection"] is not None
    assert agent["model_selection"]["light_model"]["provider"] == "openrouter"
    assert agent["engine_params"] is not None
    assert agent["engine_params"]["moa_overlay"]["enabled"] is True

