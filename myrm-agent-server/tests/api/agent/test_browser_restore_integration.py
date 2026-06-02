import json

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(override=True)

from app.main import app  # noqa: E402
from tests.api.agent.utils import get_lite_model_selection  # noqa: E402

client = TestClient(app)


def test_browser_auto_restore_integration():
    model_selection = get_lite_model_selection()

    # 1. Create a custom agent
    payload = {
        "name": "Integration Browser Agent",
        "description": "Agent with browser auto restore domains",
        "system_prompt": "You are a helpful assistant. Please use the browser tool to open https://example.com and output the title of the page.",
        "is_built_in": False,
        "agentConfig": {
            "enabledBuiltinTools": ["browser"],
            "autoRestoreDomains": ["example.com"],
        },
    }

    resp = client.post("/api/v1/user-agents", json=payload)
    assert resp.status_code == 200, f"Failed to create agent: {resp.text}"
    agent_id = resp.json()["data"]["id"]
    print(f"✅ Created Agent: {agent_id}")

    # 2. Chat with the agent
    import uuid

    chat_payload = {
        "query": "Please open https://example.com and read the title.",
        "messageId": str(uuid.uuid4()),
        "action_mode": "agent",
        "agent_id": agent_id,
        "chatId": str(uuid.uuid4()),
        "modelSelection": model_selection,
    }

    answer = ""
    with client.stream("POST", "/api/v1/agents/agent-stream", json=chat_payload) as response:
        assert response.status_code == 200, f"Chat failed: {response.read()}"
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "message":
                        answer += data.get("data", "")
                    elif data.get("type") == "error":
                        print(f"Stream error: {data}")
                except Exception:
                    pass

    print(f"Agent Answer: {answer}")
    assert len(answer) > 0
    assert "Example Domain" in answer or "example" in answer.lower()
    print("✅ Integration test passed.")
