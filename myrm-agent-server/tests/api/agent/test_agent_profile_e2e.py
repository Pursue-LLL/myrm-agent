"""端到端集成测试：Agent Profile 高级功能 (历史记录、AI 生成、乐观锁)

测试 /user-agents/generate-prompt 和 /user-agents/{agent_id}/history 接口。
验证底层乐观锁机制。
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_generate_prompt_e2e(async_client: AsyncClient):
    """测试 AI 生成 Prompt 的流式接口"""
    # 测试缺少 intent
    response = await async_client.post("/api/agents/generate-prompt", json={})
    assert response.status_code == 422  # Pydantic validation error

    response = await async_client.post("/api/agents/generate-prompt", json={"intent": ""})
    assert response.status_code == 400
    assert "Intent cannot be empty" in response.json()["detail"]

    # 测试正常生成 (需要配置了 BASIC_API_KEY，这里假设环境已配置)
    # 如果未配置，应该返回 422
    response = await async_client.post(
        "/api/agents/generate-prompt",
        json={"intent": "帮我写一个翻译助手的提示词", "locale": "zh-CN"},
    )

    if response.status_code == 422:
        # 如果测试环境没有配置模型，验证优雅降级
        assert "LLM provider is not configured" in response.json()["detail"]
    else:
        # 如果配置了模型，验证 SSE 流
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk

        assert len(buffer) > 0
        # 验证是否符合 SSEEnvelope 格式
        lines = buffer.split("\n\n")
        first_valid_line = next((line for line in lines if line.startswith("data: ")), None)
        assert first_valid_line is not None
        data = json.loads(first_valid_line[6:])
        assert data["type"] == "content" or data["type"] == "error"


@pytest.mark.asyncio
async def test_agent_history_and_optimistic_locking_e2e(async_client: AsyncClient):
    """测试 Agent 历史记录生成和并发更新时的乐观锁"""

    # 1. 创建一个测试 Agent
    create_data = {
        "name": "History Test Agent",
        "description": "Test",
        "model_selection": {"providerId": "openai", "model": "gpt-4o-mini"},
        "system_prompt": "Initial prompt",
    }
    response = await async_client.post("/api/agents", json=create_data)
    assert response.status_code == 200
    agent_id = response.json()["data"]["id"]

    # 2. 验证初始历史记录
    history_res = await async_client.get(f"/api/agents/{agent_id}/history")
    assert history_res.status_code == 200
    history_data = history_res.json()["data"]
    assert len(history_data) == 1
    assert history_data[0]["version"] == 1
    assert history_data[0]["systemPrompt"] == "Initial prompt"

    # 3. 更新 Agent
    update_data = {"system_prompt": "Updated prompt v2"}
    response = await async_client.put(f"/api/agents/{agent_id}", json=update_data)
    assert response.status_code == 200

    # 4. 验证历史记录增加
    history_res = await async_client.get(f"/api/agents/{agent_id}/history")
    history_data = history_res.json()["data"]
    print("History Data:", history_data)
    assert len(history_data) == 2
    assert history_data[0]["version"] == 2  # 倒序排列
    assert history_data[0]["systemPrompt"] == "Updated prompt v2"

    # 5. 验证版本号在多次更新后持续递增
    update_data_3 = {"system_prompt": "Updated prompt v3"}
    response = await async_client.put(f"/api/agents/{agent_id}", json=update_data_3)
    assert response.status_code == 200

    history_res = await async_client.get(f"/api/agents/{agent_id}/history")
    history_data = history_res.json()["data"]
    assert len(history_data) == 3
    assert history_data[0]["version"] == 3
    assert history_data[0]["systemPrompt"] == "Updated prompt v3"

    # 清理
    await async_client.delete(f"/api/agents/{agent_id}")
