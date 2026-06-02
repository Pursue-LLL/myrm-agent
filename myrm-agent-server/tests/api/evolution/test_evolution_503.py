import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)

def test_fix_evolution_engine_not_initialized(client):
    from unittest.mock import MagicMock, patch
    
    with patch("myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration", return_value=None), \
         patch("app.api.skills.evolution.fix._get_skill_store") as mock_store:
        
        mock_store.return_value.get_skill.return_value = MagicMock(name="mock_skill")
        
        response = client.post("/api/v1/evolution/fix/some_skill", json={"reason": "test", "force_retry": True})
        assert response.status_code == 503
        assert "Evolution engine not initialized" in response.json()["detail"]

def test_derive_evolution_engine_not_initialized(client):
    from unittest.mock import MagicMock, patch
    
    with patch("myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration", return_value=None), \
         patch("app.api.skills.evolution.derive._get_skill_store") as mock_store:
    
        mock_store.return_value.get_skill.return_value = MagicMock(name="mock_skill")
    
        response = client.post("/api/v1/evolution/derive/some_skill", json={"instruction": "test"})
        assert response.status_code == 503
        assert "Evolution engine not initialized" in response.json()["detail"]
