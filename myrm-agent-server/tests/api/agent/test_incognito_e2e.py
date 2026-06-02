from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def test_incognito_mode_stream(client: TestClient):
    model_selection = get_model_selection()
    search_request = {
        "query": "hello incognito",
        "message_id": "test-msg-id",
        "chat_id": "test_incognito_e2e",
        "action_mode": "fast",
        "search_depth": "normal",
        "model_selection": model_selection,
        "enable_memory": True,
        "incognito_mode": True,
        "timezone": "UTC"
    }
    
    with client.stream("POST", "/api/v1/agents/agent-stream", json=search_request) as response:
        assert response.status_code == 200
        content = response.read().decode("utf-8")
        print("Response:", content)
