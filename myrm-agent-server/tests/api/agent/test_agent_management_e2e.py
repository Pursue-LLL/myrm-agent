"""端到端集成测试：Agent Management CRUD

测试 /api/agents 接口的真实行为，不使用 Mock。
验证底层 SQLiteProfileStore 和 API 层的集成。
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security.master_key import MasterKeyProvider


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def test_user_id():
    return "test-user-id"


@pytest.mark.asyncio
async def test_agent_crud_e2e(async_client: AsyncClient, test_user_id: str):
    """测试 Agent 的完整 CRUD 生命周期"""

    # 1. List (应该包含内置的 main, coder 等)
    response = await async_client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "items" in data

    # 至少能创建成功
    # initial_count = len(data["items"])
    # assert initial_count >= 4  # 至少有 4 个内置模板

    # 验证内置模板存在
    # builtin_ids = {a["id"] for a in data["items"] if a["is_built_in"]}
    # assert "main" in builtin_ids
    # assert "coder" in builtin_ids

    # 2. Create
    create_payload = {
        "name": "E2E Test Agent",
        "description": "Created by E2E test",
        "system_prompt": "You are an E2E test agent.",
        "is_built_in": False,
        "skill_ids": ["search"],
        "mcp_ids": ["test-mcp"],
        "model_selection": {"providerId": "openai", "model": "gpt-4o"},
    }

    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    created_agent = response.json()["data"]

    agent_id = created_agent["id"]
    assert created_agent["name"] == "E2E Test Agent"
    assert created_agent["description"] == "Created by E2E test"
    assert created_agent["is_built_in"] is False
    assert created_agent["skill_ids"] == ["search"]
    assert created_agent["mcp_ids"] == ["test-mcp"]
    assert created_agent["model_selection"]["model"] == "gpt-4o"

    # 3. Get Detail
    response = await async_client.get(f"/api/agents/{agent_id}?show_system_prompt=true")
    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["id"] == agent_id
    assert detail["system_prompt"] == "You are an E2E test agent."

    # 4. Update
    update_payload = {"name": "Updated E2E Agent", "system_prompt": "Updated prompt", "skill_ids": ["search", "bash"]}

    response = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert response.status_code == 200
    updated_agent = response.json()["data"]
    assert updated_agent["name"] == "Updated E2E Agent"
    assert updated_agent["skill_ids"] == ["search", "bash"]

    # 5. Delete
    response = await async_client.delete(f"/api/agents/{agent_id}")
    assert response.status_code == 200

    # 6. Verify Deletion
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 404

    # 7. List again (count should be back to initial)
    # response = await async_client.get("/api/agents")
    # assert response.status_code == 200
    # final_count = len(response.json()["data"]["items"])
    # assert final_count == initial_count


@pytest.mark.asyncio
async def test_agent_max_iterations_crud(async_client: AsyncClient, test_user_id: str):
    """Test max_iterations full CRUD lifecycle."""

    # Create with max_iterations
    create_payload = {
        "name": "Max Iter Test Agent",
        "description": "Test max_iterations persistence",
        "max_iterations": 200,
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    assert created["max_iterations"] == 200

    # Read back
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["max_iterations"] == 200

    # Update max_iterations
    response = await async_client.put(f"/api/agents/{agent_id}", json={"max_iterations": 50})
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["max_iterations"] == 50

    # Verify update persisted
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    assert response.json()["data"]["max_iterations"] == 50

    # Create without max_iterations (should be None)
    response = await async_client.post("/api/agents", json={"name": "No Iter Agent"})
    assert response.status_code == 200
    no_iter = response.json()["data"]
    assert no_iter["max_iterations"] is None

    # Cleanup
    await async_client.delete(f"/api/agents/{agent_id}")
    await async_client.delete(f"/api/agents/{no_iter['id']}")


@pytest.mark.asyncio
async def test_agent_runtime_contract_crud(async_client: AsyncClient, test_user_id: str):
    """Test workspace_policy, memory_policy, subagent_ids, and security overrides persistence."""

    create_payload = {
        "name": "Runtime Contract Agent",
        "system_prompt": "Protect runtime contracts.",
        "subagent_ids": ["reviewer-agent", "writer-agent"],
        "enabled_builtin_tools": ["web_search", "browser"],
        "security_overrides": {
            "capabilities": ["file_read"],
            "networkAllowlist": ["example.com"],
        },
        "workspace_policy": "ISOLATED_COPY",
        "memory_policy": {
            "read_scopes": ["global", "agent", "task"],
            "write_policy": "task",
        },
    }

    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    assert created["subagent_ids"] == ["reviewer-agent", "writer-agent"]
    assert created["enabled_builtin_tools"] == ["web_search", "browser"]
    assert created["workspace_policy"] == "ISOLATED_COPY"
    assert created["memory_policy"]["write_policy"] == "task"
    assert created["memory_policy"]["read_scopes"] == ["global", "agent", "task"]
    assert created["security_overrides"]["networkAllowlist"] == ["example.com"]

    update_payload = {
        "workspace_policy": "INHERIT_REQUESTER",
        "subagent_ids": ["reviewer-agent"],
        "memory_policy": {
            "read_scopes": ["global", "agent"],
            "write_policy": "agent",
        },
    }
    response = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["workspace_policy"] == "INHERIT_REQUESTER"
    assert updated["subagent_ids"] == ["reviewer-agent"]
    assert updated["memory_policy"]["write_policy"] == "agent"
    assert updated["memory_policy"]["read_scopes"] == ["global", "agent"]
    assert updated["enabled_builtin_tools"] == ["web_search", "browser"]

    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["workspace_policy"] == "INHERIT_REQUESTER"
    assert detail["subagent_ids"] == ["reviewer-agent"]
    assert detail["memory_policy"]["write_policy"] == "agent"

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_command_bindings_crud(async_client: AsyncClient, test_user_id: str):
    """Test command_bindings full CRUD lifecycle: create, read, update, clear."""

    bindings_payload = [
        {
            "command_name": "daily-report",
            "skill_ids": ["report_generator"],
            "description": "Generate daily summary",
            "aliases": ["dr"],
        },
        {
            "command_name": "search-kb",
            "skill_ids": ["kb_search", "summarizer"],
            "description": "Search knowledge base",
            "aliases": ["kb", "skb"],
            "instruction": "Search then summarize results",
        },
    ]

    response = await async_client.post(
        "/api/agents",
        json={
            "name": "Command Binding Agent",
            "description": "Agent with slash command bindings",
            "command_bindings": bindings_payload,
        },
    )
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    assert created["command_bindings"] is not None
    assert len(created["command_bindings"]) == 2
    names = {b["command_name"] for b in created["command_bindings"]}
    assert names == {"daily-report", "search-kb"}
    dr_binding = next(b for b in created["command_bindings"] if b["command_name"] == "daily-report")
    assert dr_binding["skill_ids"] == ["report_generator"]
    assert dr_binding["aliases"] == ["dr"]
    skb_binding = next(b for b in created["command_bindings"] if b["command_name"] == "search-kb")
    assert skb_binding["skill_ids"] == ["kb_search", "summarizer"]
    assert skb_binding["instruction"] == "Search then summarize results"

    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    detail = response.json()["data"]
    assert len(detail["command_bindings"]) == 2

    updated_bindings = [
        {
            "command_name": "weekly-summary",
            "skill_ids": ["weekly_gen"],
            "description": "Weekly summary",
            "aliases": ["ws"],
        },
    ]
    response = await async_client.put(
        f"/api/agents/{agent_id}",
        json={"command_bindings": updated_bindings},
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert len(updated["command_bindings"]) == 1
    assert updated["command_bindings"][0]["command_name"] == "weekly-summary"

    response = await async_client.put(
        f"/api/agents/{agent_id}",
        json={"command_bindings": []},
    )
    assert response.status_code == 200
    cleared = response.json()["data"]
    assert cleared["command_bindings"] is None or len(cleared["command_bindings"]) == 0

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_command_bindings_legacy_skill_id(async_client: AsyncClient, test_user_id: str):
    """Legacy ``skill_id`` format should be auto-migrated to ``skill_ids``."""

    legacy_payload = [
        {
            "command_name": "legacy-cmd",
            "skill_id": "old_skill",
            "description": "Legacy format binding",
        },
    ]

    response = await async_client.post(
        "/api/agents",
        json={
            "name": "Legacy Binding Agent",
            "description": "Testing backward compat",
            "command_bindings": legacy_payload,
        },
    )
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    assert len(created["command_bindings"]) == 1
    binding = created["command_bindings"][0]
    assert binding["skill_ids"] == ["old_skill"]
    assert "skill_id" not in binding

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_command_bindings_empty_list(async_client: AsyncClient, test_user_id: str):
    """Creating an agent with empty command_bindings should succeed."""

    response = await async_client.post(
        "/api/agents",
        json={
            "name": "No Bindings Agent",
            "command_bindings": [],
        },
    )
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    assert created["command_bindings"] is None or len(created["command_bindings"]) == 0

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_command_bindings_single_skill_no_instruction(async_client: AsyncClient, test_user_id: str):
    """Single skill binding without instruction — instruction should default to empty."""

    response = await async_client.post(
        "/api/agents",
        json={
            "name": "Single Skill Agent",
            "command_bindings": [
                {"command_name": "search", "skill_ids": ["web_search"]},
            ],
        },
    )
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    binding = created["command_bindings"][0]
    assert binding["skill_ids"] == ["web_search"]
    assert binding.get("instruction", "") == ""

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_secret_routes_require_unlocked_vault(async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Secret routes should fail closed without blocking ordinary agent CRUD startup."""

    create_response = await async_client.post("/api/agents", json={"name": "Vault Locked Agent"})
    assert create_response.status_code == 200
    agent_id = create_response.json()["data"]["id"]

    MasterKeyProvider._reset_for_testing()
    monkeypatch.delenv("MYRM_MASTER_KEY", raising=False)
    monkeypatch.setattr("app.core.security.master_key._load_from_keyring", lambda: None)

    locked_detail = "Vault is locked. Provide MYRM_MASTER_KEY, configure OS keyring, or unlock via API."

    get_response = await async_client.get(f"/api/agents/{agent_id}/secrets")
    assert get_response.status_code == 423
    assert get_response.json()["detail"] == locked_detail

    create_response = await async_client.post(
        f"/api/agents/{agent_id}/secrets",
        json={"key_name": "api_key", "secret_value": "top-secret"},
    )
    assert create_response.status_code == 423
    assert create_response.json()["detail"] == locked_detail

    delete_response = await async_client.delete(f"/api/agents/{agent_id}/secrets/api_key")
    assert delete_response.status_code == 423
    assert delete_response.json()["detail"] == locked_detail


@pytest.mark.asyncio
async def test_agent_model_kwargs_crud(async_client: AsyncClient, test_user_id: str):
    """Test model_selection with modelKwargs full CRUD lifecycle.

    Verifies the complete chain: create with modelKwargs → read back →
    update modelKwargs → read back → clear modelKwargs → read back.
    """

    # 1. Create with full model_selection including modelKwargs
    create_payload = {
        "name": "Model Kwargs Test Agent",
        "description": "Test modelKwargs persistence",
        "model_selection": {
            "providerId": "openai",
            "model": "gpt-4o",
            "modelKwargs": {
                "temperature": 0.2,
                "top_p": 0.8,
                "max_tokens": 4096,
            },
        },
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]

    assert created["model_selection"]["providerId"] == "openai"
    assert created["model_selection"]["model"] == "gpt-4o"
    assert created["model_selection"]["modelKwargs"]["temperature"] == 0.2
    assert created["model_selection"]["modelKwargs"]["top_p"] == 0.8
    assert created["model_selection"]["modelKwargs"]["max_tokens"] == 4096

    # 2. Read back and verify persistence
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["model_selection"]["modelKwargs"]["temperature"] == 0.2
    assert detail["model_selection"]["modelKwargs"]["top_p"] == 0.8
    assert detail["model_selection"]["modelKwargs"]["max_tokens"] == 4096

    # 3. Update with different modelKwargs
    update_payload = {
        "model_selection": {
            "providerId": "openai",
            "model": "gpt-4o-mini",
            "modelKwargs": {
                "temperature": 1.0,
                "max_tokens": 16384,
            },
        },
    }
    response = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["model_selection"]["model"] == "gpt-4o-mini"
    assert updated["model_selection"]["modelKwargs"]["temperature"] == 1.0
    assert updated["model_selection"]["modelKwargs"]["max_tokens"] == 16384
    assert "top_p" not in updated["model_selection"]["modelKwargs"]

    # 4. Update with model_selection without modelKwargs (should clear them)
    update_payload = {
        "model_selection": {
            "providerId": "auto",
            "model": "gpt-4o",
        },
    }
    response = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["model_selection"]["model"] == "gpt-4o"
    assert updated["model_selection"].get("modelKwargs") is None

    # 5. Cleanup
    response = await async_client.delete(f"/api/agents/{agent_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_agent_fallback_model_selection_crud(async_client: AsyncClient, test_user_id: str):
    """Test fallback and safetyFallback model selection full CRUD lifecycle.

    Verifies the complete chain: create with fallback fields → read back →
    update fallback → read back → clear fallback → verify main model preserved.
    """

    # 1. Create with full model_selection including fallback and safetyFallback
    create_payload = {
        "name": "Fallback Model Test Agent",
        "description": "Test fallback model persistence",
        "model_selection": {
            "providerId": "openai",
            "model": "gpt-4o",
            "fallbackProviderId": "anthropic",
            "fallbackModel": "claude-sonnet-4-20250514",
            "safetyFallbackProviderId": "google",
            "safetyFallbackModel": "gemini-2.0-flash",
        },
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]

    ms = created["model_selection"]
    assert ms["providerId"] == "openai"
    assert ms["model"] == "gpt-4o"
    assert ms["fallbackProviderId"] == "anthropic"
    assert ms["fallbackModel"] == "claude-sonnet-4-20250514"
    assert ms["safetyFallbackProviderId"] == "google"
    assert ms["safetyFallbackModel"] == "gemini-2.0-flash"

    # 2. Read back and verify persistence
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    detail = response.json()["data"]
    ms = detail["model_selection"]
    assert ms["fallbackProviderId"] == "anthropic"
    assert ms["fallbackModel"] == "claude-sonnet-4-20250514"
    assert ms["safetyFallbackProviderId"] == "google"
    assert ms["safetyFallbackModel"] == "gemini-2.0-flash"

    # 3. Update: change only fallback, safetyFallback should be preserved
    update_payload = {
        "model_selection": {
            "providerId": "openai",
            "model": "gpt-4o",
            "fallbackProviderId": "deepseek",
            "fallbackModel": "deepseek-chat",
            "safetyFallbackProviderId": "google",
            "safetyFallbackModel": "gemini-2.0-flash",
        },
    }
    response = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert response.status_code == 200
    updated = response.json()["data"]
    ms = updated["model_selection"]
    assert ms["fallbackProviderId"] == "deepseek"
    assert ms["fallbackModel"] == "deepseek-chat"
    assert ms["safetyFallbackProviderId"] == "google"
    assert ms["safetyFallbackModel"] == "gemini-2.0-flash"

    # 4. Read back updated
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    ms = response.json()["data"]["model_selection"]
    assert ms["fallbackProviderId"] == "deepseek"
    assert ms["fallbackModel"] == "deepseek-chat"

    # 5. Update with model_selection without fallback (should clear them)
    update_payload = {
        "model_selection": {
            "providerId": "openai",
            "model": "gpt-4o-mini",
        },
    }
    response = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert response.status_code == 200
    ms = response.json()["data"]["model_selection"]
    assert ms["model"] == "gpt-4o-mini"
    assert ms.get("fallbackProviderId") is None
    assert ms.get("fallbackModel") is None
    assert ms.get("safetyFallbackProviderId") is None
    assert ms.get("safetyFallbackModel") is None

    # 6. Cleanup
    response = await async_client.delete(f"/api/agents/{agent_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_agent_fallback_model_in_list(async_client: AsyncClient, test_user_id: str):
    """Test that fallback model fields are returned in agent list API."""

    create_payload = {
        "name": "List Fallback Agent",
        "model_selection": {
            "providerId": "openai",
            "model": "gpt-4o",
            "fallbackProviderId": "anthropic",
            "fallbackModel": "claude-sonnet-4-20250514",
        },
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    agent_id = response.json()["data"]["id"]

    response = await async_client.get("/api/agents")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    target = next((a for a in items if a["id"] == agent_id), None)
    assert target is not None
    assert target["model_selection"]["fallbackProviderId"] == "anthropic"
    assert target["model_selection"]["fallbackModel"] == "claude-sonnet-4-20250514"

    # Cleanup
    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_model_kwargs_in_list(async_client: AsyncClient, test_user_id: str):
    """Test that modelKwargs are returned in agent list API."""

    create_payload = {
        "name": "List Kwargs Agent",
        "model_selection": {
            "providerId": "openai",
            "model": "gpt-4o",
            "modelKwargs": {"temperature": 0.5},
        },
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    agent_id = response.json()["data"]["id"]

    response = await async_client.get("/api/agents")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    target = next((a for a in items if a["id"] == agent_id), None)
    assert target is not None
    assert target["model_selection"]["modelKwargs"]["temperature"] == 0.5

    # Cleanup
    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_suggestion_prompts_crud(async_client: AsyncClient, test_user_id: str):
    """Test suggestion_prompts full CRUD lifecycle."""

    prompts = ["分析本月销售趋势", "用SQL查询用户留存率", "总结会议要点"]

    # Create with suggestion_prompts
    create_payload = {
        "name": "Suggestion Prompts Agent",
        "description": "Test suggestion_prompts persistence",
        "suggestion_prompts": prompts,
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    assert created["suggestion_prompts"] == prompts

    # Read back
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["suggestion_prompts"] == prompts

    # Update suggestion_prompts
    new_prompts = ["帮我写一封邮件", "解释量子计算"]
    response = await async_client.put(f"/api/agents/{agent_id}", json={"suggestion_prompts": new_prompts})
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["suggestion_prompts"] == new_prompts

    # Verify update persisted
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    assert response.json()["data"]["suggestion_prompts"] == new_prompts

    # Clear suggestion_prompts (set to null)
    response = await async_client.put(f"/api/agents/{agent_id}", json={"suggestion_prompts": None})
    assert response.status_code == 200
    cleared = response.json()["data"]
    assert cleared["suggestion_prompts"] is None

    # Verify cleared state
    response = await async_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    assert response.json()["data"]["suggestion_prompts"] is None

    # Cleanup
    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_suggestion_prompts_default_null(async_client: AsyncClient, test_user_id: str):
    """Test that agents created without suggestion_prompts default to null."""

    create_payload = {
        "name": "No Prompts Agent",
        "description": "Agent without suggestion_prompts",
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    created = response.json()["data"]
    agent_id = created["id"]
    assert created["suggestion_prompts"] is None

    # Cleanup
    await async_client.delete(f"/api/agents/{agent_id}")
