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
