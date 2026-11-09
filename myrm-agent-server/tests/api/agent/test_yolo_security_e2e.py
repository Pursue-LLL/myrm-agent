"""YOLO Mode 端到端集成测试

真实测试 Agent CRUD API 中 YOLO Mode 安全配置的注入和传播。

使用 in-memory SQLite + 真实 FastAPI 应用，不 mock 核心业务逻辑。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _create_test_agent(client: AsyncClient, **overrides) -> dict:
    payload = {
        "name": "YOLO Test Agent",
        "description": "For YOLO E2E test",
        "system_prompt": "You are a test agent.",
        "is_built_in": False,
        **overrides,
    }
    resp = await client.post("/api/agents", json=payload)
    assert resp.status_code == 200, f"Create failed: {resp.text}"
    return resp.json()["data"]


# ─── YOLO Mode 安全配置 ───


class TestYoloSecurityConfig:
    """YOLO Mode 通过 security_overrides 的注入和传播。"""

    @pytest.mark.asyncio
    async def test_create_agent_with_yolo_security_overrides(self, async_client: AsyncClient) -> None:
        """Agent 的 security_overrides 可以包含 YOLO 配置。"""
        overrides = {"yoloModeEnabled": True, "yolo_mode_timeout": 600}
        agent = await _create_test_agent(async_client, security_overrides=overrides)
        assert agent["security_overrides"]["yoloModeEnabled"] is True
        assert agent["security_overrides"]["yolo_mode_timeout"] == 600

    @pytest.mark.asyncio
    async def test_create_agent_yolo_overrides_returned(self, async_client: AsyncClient) -> None:
        """创建 Agent 时 YOLO security_overrides 在 create 响应中返回。"""
        overrides = {"yoloModeEnabled": True, "yolo_mode_timeout": 600}
        agent = await _create_test_agent(async_client, security_overrides=overrides)
        assert agent["security_overrides"]["yoloModeEnabled"] is True
        assert agent["security_overrides"]["yolo_mode_timeout"] == 600

    @pytest.mark.asyncio
    async def test_yolo_config_parsed_to_security_config(self) -> None:
        """验证 YOLO 字段能被 parse_security_config 正确解析。"""
        from myrm_agent_harness.agent.security.config import parse_security_config

        raw = {
            "yoloModeEnabled": True,
            "yolo_mode_timeout": 300,
            "approvalTimeoutSeconds": 60,
        }
        config = parse_security_config(raw)
        assert config is not None
        assert config.yolo_mode_enabled is True
        assert config.yolo_mode_timeout == 300

    @pytest.mark.asyncio
    async def test_yolo_channel_preset_merge(self) -> None:
        """验证 user + agent YOLO 配置的 OR 合并语义。"""
        from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config

        config = build_channel_security_config(
            "web_chat",
            {"yolo_mode_enabled": False},
            agent_security_raw={"yolo_mode_enabled": True, "yolo_mode_timeout": 120},
        )
        assert config.yolo_mode_enabled is True
        assert config.yolo_mode_timeout == 120


# ─── Agent 生命周期中的 YOLO 配置 ───


class TestYoloAgentLifecycle:
    """YOLO security_overrides 在更新与删除中的行为。"""

    @pytest.mark.asyncio
    async def test_update_other_fields_preserves_yolo(self, async_client: AsyncClient) -> None:
        """更新其他字段不影响 YOLO security_overrides。"""
        agent = await _create_test_agent(
            async_client,
            security_overrides={"yoloModeEnabled": True, "yolo_mode_timeout": 300},
        )

        resp = await async_client.put(f"/api/agents/{agent['id']}", json={"description": "Updated description"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["description"] == "Updated description"
        assert data["security_overrides"]["yoloModeEnabled"] is True

    @pytest.mark.asyncio
    async def test_deleted_agent_is_gone(self, async_client: AsyncClient) -> None:
        """删除 Agent 后无法再获取。"""
        agent = await _create_test_agent(async_client)

        resp = await async_client.delete(f"/api/agents/{agent['id']}")
        assert resp.status_code == 200

        resp = await async_client.get(f"/api/agents/{agent['id']}")
        assert resp.status_code == 404
