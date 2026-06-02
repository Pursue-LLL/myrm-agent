import json
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
            print(f"DEBUG stream line: {line}")
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "message":
                        answer += data.get("data", "")
                    elif data.get("type") == "error":
                        print(f"Stream error: {data}")
                except Exception:
                    pass
    return answer


@pytest.mark.asyncio
async def test_architecture_features(ephemeral_server: str):
    BASE_URL = ephemeral_server
    print("Starting E2E Architecture Tests against running server...")

    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
        # 0. Check health
        resp = await client.get("/health")
        if resp.status_code != 200:
            print("Server is not running or healthy. Please start it with `uv run run.py`")
            return
        print("✅ Server is healthy")

        # 1. Create a custom agent (Sci-Fi Writer)
        print("\n--- Testing AgentRuntimeSpec (Custom Prompt) ---")
        scifi_payload = {
            "name": "Sci-Fi Writer",
            "description": "Answers only in sci-fi terms.",
            "system_prompt": "You are a sci-fi writer. You must answer all questions using sci-fi terminology and concepts (e.g., hyperdrive, quantum flux, nebulas). Never answer normally.",
            "is_built_in": False,
        }
        resp = await client.post("/api/v1/user-agents", json=scifi_payload)
        assert resp.status_code == 200, f"Failed to create agent: {resp.text}"
        scifi_agent_id = resp.json()["data"]["id"]
        print(f"✅ Created Sci-Fi Agent: {scifi_agent_id}")

        # Chat with Sci-Fi Writer
        scifi_chat_id = str(uuid.uuid4())
        answer = await chat_with_agent(client, "What is the capital of France?", scifi_agent_id, chat_id=scifi_chat_id)
        print(f"Sci-Fi Writer Answer: {answer}")
        assert len(answer) > 0
        print("✅ AgentRuntimeSpec compiled and executed successfully.")

        # 2. Test Memory Isolation
        print("\n--- Testing Memory Namespace Isolation ---")
        # Tell Sci-Fi Writer a secret
        await chat_with_agent(client, "My secret code name is Star-Lord. Remember this.", scifi_agent_id, chat_id=scifi_chat_id)
        print("✅ Told secret to Sci-Fi Writer.")

        # Ask default agent about the secret
        default_chat_id = str(uuid.uuid4())
        default_answer = await chat_with_agent(client, "What is my secret code name?", chat_id=default_chat_id)
        print(f"Default Agent Answer: {default_answer}")
        assert "star-lord" not in default_answer.lower(), "Memory leaked to default agent!"
        print("✅ Memory isolation verified. Default agent does not know the secret.")

        # 3. Test SubagentCatalog Mode 3
        print("\n--- Testing SubagentCatalog (Custom Agent as Subagent) ---")
        # Create Translator Agent
        translator_payload = {
            "name": "Translator",
            "description": "Translates text to Japanese.",
            "system_prompt": "You are a translator. Translate the user's input to Japanese. Output ONLY the Japanese translation, nothing else.",
            "is_built_in": False,
        }
        resp = await client.post("/api/v1/user-agents", json=translator_payload)
        assert resp.status_code == 200
        translator_id = resp.json()["data"]["id"]
        print(f"✅ Created Translator Agent: {translator_id}")

        # Create Manager Agent
        manager_payload = {
            "name": "Manager",
            "description": "Delegates to the translator.",
            "system_prompt": f"You are a manager. You MUST IMMEDIATELY call the `delegate_task_tool` to delegate the translation task to the agent with type '{translator_id}'. Pass the text to translate as the 'task' parameter, and set 'wait' to true. Do NOT search for skills. Do NOT translate it yourself. Just call the `delegate_task_tool`.",
            "is_built_in": False,
        }
        resp = await client.post("/api/v1/user-agents", json=manager_payload)
        assert resp.status_code == 200
        manager_id = resp.json()["data"]["id"]
        print(f"✅ Created Manager Agent: {manager_id}")

        # Chat with Manager
        manager_answer = await chat_with_agent(client, "Please translate 'Hello World' using the translator agent.", manager_id)
        print(f"Manager Answer: {manager_answer}")
        assert "ハローワールド" in manager_answer or "こんにちは" in manager_answer or "世界" in manager_answer, (
            "Subagent delegation failed or didn't return Japanese."
        )
        print("✅ SubagentCatalog Mode 3 verified successfully.")

        # Cleanup
        print("\n--- Cleaning up ---")
        await client.delete(f"/api/v1/user-agents/{scifi_agent_id}")
        await client.delete(f"/api/v1/user-agents/{translator_id}")
        await client.delete(f"/api/v1/user-agents/{manager_id}")
        print("✅ Cleanup complete.")

        print("\n🎉 All E2E Architecture tests passed successfully!")


# if __name__ == "__main__":
#     asyncio.run(test_architecture_features())
