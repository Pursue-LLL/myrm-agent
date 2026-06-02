"""端到端集成测试：Agent Management 边缘场景与关联资源

测试 /api/agents 接口的异常处理、Avatar 上传、统计信息等。
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def test_user_id():
    return "test-user-id"


@pytest.mark.asyncio
async def test_agent_duplicate_creation(async_client: AsyncClient, test_user_id: str):
    """测试重复创建同名 Agent"""
    payload = {
        "name": "Duplicate Test Agent",
        "description": "Test",
    }

    # 第一次创建
    res1 = await async_client.post("/api/agents", json=payload)
    assert res1.status_code == 200
    agent_id = res1.json()["data"]["id"]

    # 第二次创建同名 Agent（单机沙箱模式下，ProfileManager 允许同名，但 ID 会自动生成新的）
    # 如果业务层有名称唯一性约束，则会报错。目前 Server 层已移除 agents 表，所以允许同名不同 ID。
    res2 = await async_client.post("/api/agents", json=payload)
    assert res2.status_code == 200
    assert res2.json()["data"]["id"] != agent_id

    # 清理
    await async_client.delete(f"/api/agents/{agent_id}")
    await async_client.delete(f"/api/agents/{res2.json()['data']['id']}")


@pytest.mark.asyncio
async def test_agent_update_not_found(async_client: AsyncClient, test_user_id: str):
    """测试更新不存在的 Agent"""
    payload = {"name": "New Name"}
    res = await async_client.put("/api/agents/non-existent-id", json=payload)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_agent_delete_not_found(async_client: AsyncClient, test_user_id: str):
    """测试删除不存在的 Agent"""
    res = await async_client.delete("/api/agents/non-existent-id")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_agent_partial_update(async_client: AsyncClient, test_user_id: str):
    """测试部分更新（PATCH 语义）"""
    # 创建
    payload = {
        "name": "Partial Update Agent",
        "description": "Original Description",
        "system_prompt": "Original Prompt",
        "skill_ids": ["search"],
    }
    res = await async_client.post("/api/agents", json=payload)
    agent_id = res.json()["data"]["id"]

    # 只更新 Prompt 和 Skills
    update_payload = {"system_prompt": "New Prompt", "skill_ids": ["bash"]}
    res = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
    assert res.status_code == 200

    # 验证其他字段未变
    res = await async_client.get(f"/api/agents/{agent_id}?show_system_prompt=true")
    data = res.json()["data"]
    assert data["name"] == "Partial Update Agent"
    assert data["description"] == "Original Description"
    assert data["system_prompt"] == "New Prompt"
    assert data["skill_ids"] == ["bash"]

    # 清理
    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_avatar_upload(async_client: AsyncClient, test_user_id: str):
    """测试头像上传"""
    # 创建
    res = await async_client.post("/api/agents", json={"name": "Avatar Agent"})
    agent_id = res.json()["data"]["id"]

    # 构造一个 1x1 像素的假 PNG 文件
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff\xff\x7f\x00\x08\xfc\x02\xfe\xa7\x18\x9f\x00\x00\x00\x00IEND\xaeB`\x82"

    files = {"file": ("test.png", fake_png, "image/png")}
    res = await async_client.post(f"/api/agents/{agent_id}/avatar", files=files)

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["avatar_url"].startswith("home://")
    assert data["avatar_url"].endswith(".png")
    assert os.path.exists(data["local_path"])

    # 验证 Agent Profile 已更新
    res = await async_client.get(f"/api/agents/{agent_id}")
    assert res.json()["data"]["avatar_url"] == data["avatar_url"]

    # 清理
    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_builtin_agent_update_blocked(async_client: AsyncClient, test_user_id: str):
    """Built-in agents must not be updatable via API."""
    res = await async_client.post(
        "/api/agents",
        json={"name": "Built-in Guard", "is_built_in": True},
    )
    assert res.status_code == 200
    agent_id = res.json()["data"]["id"]

    update_res = await async_client.put(
        f"/api/agents/{agent_id}", json={"name": "Hacked Name"}
    )
    assert update_res.status_code == 403

    get_res = await async_client.get(f"/api/agents/{agent_id}")
    assert get_res.json()["data"]["name"] == "Built-in Guard"


@pytest.mark.asyncio
async def test_builtin_agent_delete_blocked(async_client: AsyncClient, test_user_id: str):
    """Built-in agents must not be deletable via API."""
    res = await async_client.post(
        "/api/agents",
        json={"name": "Built-in Delete Guard", "is_built_in": True},
    )
    assert res.status_code == 200
    agent_id = res.json()["data"]["id"]

    delete_res = await async_client.delete(f"/api/agents/{agent_id}")
    assert delete_res.status_code == 403

    get_res = await async_client.get(f"/api/agents/{agent_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["name"] == "Built-in Delete Guard"


@pytest.mark.asyncio
async def test_agent_statistics(async_client: AsyncClient, test_user_id: str):
    """测试统计 API"""
    # 创建
    res = await async_client.post("/api/agents", json={"name": "Stats Agent"})
    agent_id = res.json()["data"]["id"]

    # 获取统计
    res = await async_client.get(f"/api/agents/{agent_id}/statistics")
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["agent_id"] == agent_id
    assert data["agent_name"] == "Stats Agent"
    assert data["total_sessions"] >= 0
    assert data["total_messages"] >= 0

    # 清理
    await async_client.delete(f"/api/agents/{agent_id}")
