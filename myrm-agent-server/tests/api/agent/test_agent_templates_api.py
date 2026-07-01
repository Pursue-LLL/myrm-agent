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


def test_list_templates_includes_batch_processing_assistant(client: TestClient):
    """Batch processing template is exposed in Template Market."""
    response = client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    templates = response.json()["data"]
    batch = next((t for t in templates if t.get("id") == "batch_processing_assistant"), None)
    assert batch is not None, "batch_processing_assistant seed missing from catalog"
    assert batch.get("agent_type") == "individual"
    assert batch.get("name")


def test_instantiate_batch_processing_assistant_enables_llm_map(client: TestClient):
    """Instantiate batch template → agent persists llm_map in enabled_builtin_tools."""
    response = client.post("/api/v1/agents/instantiate-template/batch_processing_assistant")
    assert response.status_code == 200, response.text
    agent = response.json()["data"]
    agent_id = agent["id"]
    try:
        tools = agent.get("enabled_builtin_tools") or []
        assert "llm_map" in tools
        assert "answer_tool" in tools
        detail = client.get(f"/api/agents/{agent_id}?show_system_prompt=true")
        assert detail.status_code == 200
        prompt = detail.json()["data"].get("system_prompt") or ""
        assert "llm_map_tool" in prompt
    finally:
        client.delete(f"/api/agents/{agent_id}")
