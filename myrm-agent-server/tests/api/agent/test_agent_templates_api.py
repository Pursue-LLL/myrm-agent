import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_templates(client: AsyncClient):
    """Test listing agent templates."""
    response = await client.get("/api/v1/agents/templates")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    templates = data["data"]
    assert isinstance(templates, list)
    
    # Verify template structure if any exist
    if len(templates) > 0:
        first = templates[0]
        assert "id" in first
        assert "name" in first
        assert "agent_type" in first

@pytest.mark.asyncio
async def test_instantiate_template_not_found(client: AsyncClient):
    """Test instantiating a non-existent template."""
    response = await client.post("/api/v1/agents/instantiate-template/non_existent_template_123")
    assert response.status_code == 404
    
# Note: We don't test successful instantiation here because it requires a valid template file
# and might modify the database state (creating skills/agents).
