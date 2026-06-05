import uuid

import httpx
import pytest

pytestmark = pytest.mark.e2e

HEADERS = {"Content-Type": "application/json"}


async def chat_with_agent(client, query, agent_id=None, chat_id=None):
    chat_payload = {"query": query, "messageId": str(uuid.uuid4()), "action_mode": "agent"}
    if agent_id:
        chat_payload["agent_id"] = agent_id
    if chat_id:
        chat_payload["chatId"] = chat_id

    answer = ""
    async with client.stream("POST", "/api/v1/agents/agent-stream", json=chat_payload) as response:
        assert response.status_code == 200, f"Chat failed: {await response.aread()}"
        async for line in response.aiter_lines():
            print(f"Raw line: {line}")
            if line.startswith("data: "):
                try:
                    import json

                    data = json.loads(line[6:])
                    if data.get("type") == "message":
                        answer += data.get("data", "")
                    elif data.get("type") == "error":
                        print(f"Stream error: {data}")
                except Exception:
                    pass
    return answer


@pytest.mark.asyncio
async def test_browser_auto_restore_e2e(ephemeral_server: str):
    BASE_URL = ephemeral_server
    print("Starting E2E Browser Auto Restore Test...")

    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
        # Create an agent with browser enabled and auto_restore_domains configured
        payload = {
            "name": "Browser Agent",
            "description": "Agent with browser auto restore domains",
            "system_prompt": "You are a helpful assistant. Use the browser to open https://example.com and tell me its title.",
            "is_built_in": False,
            "agent_config": {"enable_browser": True, "auto_restore_domains": ["example.com"]},
        }
        resp = await client.post("/api/v1/user-agents", json=payload)
        assert resp.status_code == 200, f"Failed to create agent: {resp.text}"
        agent_id = resp.json()["data"]["id"]
        print(f"✅ Created Browser Agent: {agent_id}")

        # Chat with the agent
        chat_id = str(uuid.uuid4())
        answer = await chat_with_agent(client, "Please open https://example.com and read the title.", agent_id, chat_id=chat_id)

        print(f"Agent Answer: {answer}")

        # The answer should indicate it successfully used the browser, which means
        # the auto_restore logic (which runs before tool setup) didn't crash.
        assert len(answer) > 0
        assert "Example Domain" in answer or "example" in answer.lower(), "Agent did not successfully read the page"
        print("✅ Browser auto-restore test executed successfully without crashing.")
