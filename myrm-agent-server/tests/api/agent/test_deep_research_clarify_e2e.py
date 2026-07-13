"""Deep Research API gate E2E

Deep Research is REMOVED from the product surface. agent-stream must reject deep_research actionMode.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection, get_search_service_config


@pytest.mark.e2e
class TestDeepResearchClarifyE2E:
    """Deep Research is disabled — agent-stream returns 403."""

    def test_deep_research_action_mode_blocked(self, client: TestClient) -> None:
        message_id = str(uuid.uuid4())
        search_request: dict[str, object] = {
            "messageId": message_id,
            "query": "帮我调研一下那个很火的AI框架，对比一下它的优缺点。",
            "modelSelection": get_model_selection(),
            "searchServiceCfg": get_search_service_config(),
            "actionMode": "deep_research",
            "agentConfig": {
                "deepResearch": {
                    "enableClarification": True,
                    "maxCycles": 0,
                }
            },
        }

        response = client.post("/api/v1/agents/agent-stream", json=search_request)
        assert response.status_code == 403
        body = response.json()
        assert "Feature Gate" in str(body.get("detail", "")) or "disabled" in str(body.get("detail", "")).lower()
