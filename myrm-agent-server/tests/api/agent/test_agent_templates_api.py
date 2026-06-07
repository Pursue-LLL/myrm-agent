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
