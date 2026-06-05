"""端到端集成测试：Agent Import/Export 功能

测试 /api/v1/api/agents/{agent_id}/export 和 /api/v1/api/agents/import 接口。
验证全量配置的导出和导入逻辑。
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_agent_import_export_e2e(async_client: AsyncClient):
    """测试 Agent 配置的导出和导入"""

    # 1. 创建一个测试 Agent，包含复杂的依赖和配置
    create_data = {
        "name": "Export Test Agent",
        "description": "An agent to be exported",
        "model_selection": {"providerId": "openai", "model": "gpt-4o"},
        "system_prompt": "You are an export expert.",
        "mcp_ids": ["mcp-1", "mcp-2"],
        "skill_ids": ["skill-1"],
        "is_built_in": False,
    }

    # 模拟真实路由：/api/agents 相当于代理的 /api/agents (参考 test_agent_profile_e2e.py，假设 prefix 是 /api/agents)
    response = await async_client.post("/api/agents", json=create_data)
    assert response.status_code == 200, f"Create agent failed: {response.text}"
    agent_id = response.json()["data"]["id"]

    try:
        # 2. 导出 Agent
        export_res = await async_client.get(f"/api/agents/{agent_id}/export")
        assert export_res.status_code == 200, f"Export agent failed: {export_res.text}"

        exported_data = export_res.json()["data"]

        # 验证导出的数据包含预期字段，并且不包含敏感/内部字段
        assert exported_data["name"] == "Export Test Agent"
        assert exported_data["system_prompt"] == "You are an export expert."
        assert exported_data["mcp_ids"] == ["mcp-1", "mcp-2"]
        assert exported_data["skill_ids"] == ["skill-1"]

        assert "id" not in exported_data
        assert "user_id" not in exported_data
        assert "created_at" not in exported_data
        assert "updated_at" not in exported_data

        # 3. 修改导出数据的名称，用于导入测试
        imported_data = exported_data.copy()
        imported_data["name"] = "Imported Test Agent"

        # 验证导入时没有 name 会失败
        invalid_import_data = exported_data.copy()
        invalid_import_data["name"] = "   "
        invalid_import_res = await async_client.post("/api/agents/import", json=invalid_import_data)
        assert invalid_import_res.status_code == 400
        assert "Agent name cannot be empty" in invalid_import_res.json()["detail"]["message"]

        # 4. 执行正常的导入
        import_res = await async_client.post("/api/agents/import", json=imported_data)
        assert import_res.status_code == 200, f"Import agent failed: {import_res.text}"

        imported_agent = import_res.json()["data"]
        imported_agent_id = imported_agent["id"]

        # 验证导入生成的 Agent 配置和之前导出的数据一致
        assert imported_agent["id"] != agent_id  # UUID 是新生成的
        assert imported_agent["name"] == "Imported Test Agent"
        # 默认返回会隐藏 prompt，这是预期的
        assert imported_agent["system_prompt"] == "⚠️ [Hidden for security]"

        # 再次通过 export 接口获取，验证 DB 中真实保存的 system_prompt
        verify_res = await async_client.get(f"/api/agents/{imported_agent_id}/export")
        assert verify_res.json()["data"]["system_prompt"] == "You are an export expert."
        assert imported_agent["mcp_ids"] == ["mcp-1", "mcp-2"]
        assert imported_agent["skill_ids"] == ["skill-1"]
        assert imported_agent["is_built_in"] is False  # 即使导入数据里有其他值也会被强制改为 False

        # 5. 清理导入生成的 Agent
        await async_client.delete(f"/api/agents/{imported_agent_id}")

    finally:
        # 清理原始测试 Agent
        await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_clone_e2e(async_client: AsyncClient):
    """Test one-click agent cloning with proper isolation."""

    create_data = {
        "name": "Clone Source Agent",
        "description": "Agent to be cloned",
        "system_prompt": "You are the original.",
        "home_directory": "/tmp/test-agent-home",
        "avatar_url": "home://avatar.png",
        "mcp_ids": ["mcp-clone"],
        "skill_ids": ["skill-clone"],
        "is_built_in": False,
    }

    response = await async_client.post("/api/agents", json=create_data)
    assert response.status_code == 200
    source_id = response.json()["data"]["id"]

    cloned_ids: list[str] = []
    try:
        # Clone with custom name
        clone_res = await async_client.post(
            f"/api/agents/{source_id}/clone",
            json={"name": "My Custom Clone"},
        )
        assert clone_res.status_code == 200
        cloned = clone_res.json()["data"]
        cloned_ids.append(cloned["id"])

        assert cloned["id"] != source_id
        assert cloned["name"] == "My Custom Clone"
        assert cloned["is_built_in"] is False
        assert cloned["home_directory"] is None
        assert cloned["avatar_url"] is None
        assert cloned["mcp_ids"] == ["mcp-clone"]
        assert cloned["skill_ids"] == ["skill-clone"]

        # Verify system_prompt is copied (via export)
        export_res = await async_client.get(f"/api/agents/{cloned['id']}/export")
        assert export_res.json()["data"]["system_prompt"] == "You are the original."

        # Clone without custom name (default "... (Copy)")
        clone_res2 = await async_client.post(f"/api/agents/{source_id}/clone")
        assert clone_res2.status_code == 200
        cloned2 = clone_res2.json()["data"]
        cloned_ids.append(cloned2["id"])
        assert cloned2["name"] == "Clone Source Agent (Copy)"

        # Clone non-existent agent
        clone_404 = await async_client.post(
            "/api/agents/non-existent-id/clone",
            json={"name": "Should fail"},
        )
        assert clone_404.status_code == 404

    finally:
        for cid in cloned_ids:
            await async_client.delete(f"/api/agents/{cid}")
        await async_client.delete(f"/api/agents/{source_id}")
