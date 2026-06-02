"""End-to-end tests for the Agent Architecture (AgentRuntimeSpec, SubagentCatalog, Memory Namespaces).

These tests run against the real database and real LLMs (no mocks).
"""

import os

import pytest
from httpx import AsyncClient

from app.database.dto import AgentCreate, ModelSelection
from app.platform_utils import get_session_factory
from app.services.agent.agent_service import AgentService

# Use the real API key configured in the environment
# Make sure BASIC_API_KEY is set in the environment or .env
os.environ["DEPLOY_MODE"] = "tauri"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy test, endpoints no longer exist")
async def test_e2e_agent_architecture(async_client: AsyncClient, test_user_id: str):
    """
    Comprehensive E2E test covering:
    1. AgentRuntimeSpec compilation (custom system prompt)
    2. Memory Namespace isolation (agent-private memory)
    3. SubagentCatalog Mode 3 (custom agent as subagent)
    """
    session_factory = get_session_factory()

    # 1. Create a custom agent (Sci-Fi Writer)
    scifi_agent_data = AgentCreate(
        name="Sci-Fi Writer",
        description="Answers only in sci-fi terms.",
        system_prompt="You are a sci-fi writer. You must answer all questions using sci-fi terminology and concepts (e.g., hyperdrive, quantum flux, nebulas). Never answer normally.",
        model_selection=ModelSelection(model="gpt-4o-mini", provider="openai"),
        is_built_in=False,
    )

    async with session_factory() as _db:
        scifi_agent = await AgentService.create_agent(scifi_agent_data, test_user_id)

    assert scifi_agent.id is not None

    # 2. Chat with the Sci-Fi Writer (Verify AgentRuntimeSpec)
    response = await async_client.post(
        "/api/v1/agents/chat",
        json={"query": "What is the capital of France?", "agent_id": scifi_agent.id, "stream": False},
        headers={"X-User-Id": test_user_id},
    )

    assert response.status_code == 200
    data = response.json()
    answer = data.get("answer", "").lower()

    # The answer should contain sci-fi terms instead of just "Paris"
    assert "paris" in answer or "france" in answer  # It should still answer the question
    # We expect some sci-fi flavor, but LLM outputs vary. We just ensure it ran successfully.
    assert len(answer) > 0

    # 3. Test Memory Isolation (Namespaces)
    # Tell Sci-Fi Writer a secret
    secret_response = await async_client.post(
        "/api/v1/agents/chat",
        json={"query": "My secret code name is Star-Lord.", "agent_id": scifi_agent.id, "stream": False},
        headers={"X-User-Id": test_user_id},
    )
    assert secret_response.status_code == 200

    # Ask the default agent (no agent_id) about the secret
    default_response = await async_client.post(
        "/api/v1/agents/chat",
        json={"query": "What is my secret code name?", "stream": False},
        headers={"X-User-Id": test_user_id},
    )
    assert default_response.status_code == 200
    default_data = default_response.json()
    default_answer = default_data.get("answer", "").lower()

    # The default agent should NOT know the secret name (Star-Lord)
    assert "star-lord" not in default_answer

    # 4. Test SubagentCatalog Mode 3 (Custom Agent as Subagent)
    # Create a Translator Agent
    translator_data = AgentCreate(
        name="Translator",
        description="Translates text to Japanese.",
        system_prompt="You are a translator. Translate the user's input to Japanese. Output ONLY the Japanese translation, nothing else.",
        model_selection=ModelSelection(model="gpt-4o-mini", provider="openai"),
        is_built_in=False,
    )

    async with session_factory() as _db:
        translator_agent = await AgentService.create_agent(translator_data, test_user_id)

    # Create a Manager Agent that delegates to the Translator
    manager_data = AgentCreate(
        name="Manager",
        description="Delegates to the translator.",
        system_prompt=f"You are a manager. You MUST use the `delegate_task` to delegate the translation task to the agent with type '{translator_agent.id}'. Pass the text to translate as the 'task' parameter, and set 'wait' to true.",
        model_selection=ModelSelection(model="gpt-4o-mini", provider="openai"),
        is_built_in=False,
    )

    async with session_factory() as _db:
        manager_agent = await AgentService.create_agent(manager_data, test_user_id)

    # Chat with the Manager
    manager_response = await async_client.post(
        "/api/v1/agents/chat",
        json={
            "query": "Please translate 'Hello World' using the translator agent.",
            "agent_id": manager_agent.id,
            "stream": False,
        },
        headers={"X-User-Id": test_user_id},
    )

    assert manager_response.status_code == 200
    manager_data_resp = manager_response.json()
    manager_answer = manager_data_resp.get("answer", "")

    # The manager should have successfully used the subagent and returned the Japanese translation
    assert "ハローワールド" in manager_answer or "こんにちは世界" in manager_answer or "こんにちは" in manager_answer

    # Cleanup
    async with session_factory() as _db:
        await AgentService.delete_agent(scifi_agent.id, test_user_id)
        await AgentService.delete_agent(translator_agent.id, test_user_id)
        await AgentService.delete_agent(manager_agent.id, test_user_id)
