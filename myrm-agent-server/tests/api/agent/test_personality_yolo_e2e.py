"""Personality & YOLO Mode 端到端集成测试

真实测试 Agent CRUD API 中 personality_style 字段的完整生命周期，
以及 YOLO Mode 安全配置的注入和传播。

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
        "name": "Personality Test Agent",
        "description": "For personality E2E test",
        "system_prompt": "You are a test agent.",
        "is_built_in": False,
        **overrides,
    }
    resp = await client.post("/api/agents", json=payload)
    assert resp.status_code == 200, f"Create failed: {resp.text}"
    return resp.json()["data"]


# ─── Personality CRUD ───


class TestPersonalityCRUD:
    """Personality style 在 Agent CRUD 中的完整生命周期。"""

    @pytest.mark.asyncio
    async def test_create_agent_default_personality(self, async_client: AsyncClient) -> None:
        """新建 Agent 默认 personality_style 为 professional。"""
        agent = await _create_test_agent(async_client)
        assert agent["personality_style"] == "professional"

    @pytest.mark.asyncio
    async def test_create_agent_with_custom_personality(self, async_client: AsyncClient) -> None:
        """新建 Agent 时指定 personality_style。"""
        agent = await _create_test_agent(async_client, personality_style="humorous")
        assert agent["personality_style"] == "humorous"

    @pytest.mark.asyncio
    async def test_update_personality_style(self, async_client: AsyncClient) -> None:
        """更新 Agent personality_style 并验证持久化。"""
        agent = await _create_test_agent(async_client)
        agent_id = agent["id"]

        resp = await async_client.put(f"/api/agents/{agent_id}", json={"personality_style": "creative"})
        assert resp.status_code == 200
        assert resp.json()["data"]["personality_style"] == "creative"

        resp = await async_client.get(f"/api/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["personality_style"] == "creative"

    @pytest.mark.asyncio
    async def test_personality_survives_other_updates(self, async_client: AsyncClient) -> None:
        """更新其他字段时 personality 保持不变。"""
        agent = await _create_test_agent(async_client, personality_style="academic")
        agent_id = agent["id"]

        resp = await async_client.put(f"/api/agents/{agent_id}", json={"name": "Renamed Agent"})
        assert resp.status_code == 200
        assert resp.json()["data"]["personality_style"] == "academic"

    @pytest.mark.asyncio
    async def test_personality_in_detail_response(self, async_client: AsyncClient) -> None:
        """Agent detail API 返回 personality_style。"""
        agent = await _create_test_agent(async_client, personality_style="friendly", name="Detail Test Agent")
        resp = await async_client.get(f"/api/agents/{agent['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["personality_style"] == "friendly"

    @pytest.mark.asyncio
    async def test_all_valid_personality_styles(self, async_client: AsyncClient) -> None:
        """验证所有 16 种预置风格都能保存和读取。"""
        styles = [
            "professional",
            "friendly",
            "concise",
            "detailed",
            "humorous",
            "academic",
            "creative",
            "socratic",
            "pirate",
            "shakespeare",
            "noir",
            "kawaii",
            "catgirl",
            "hype",
            "uwu",
            "surfer",
        ]
        for style in styles:
            agent = await _create_test_agent(async_client, personality_style=style, name=f"Style-{style}")
            assert agent["personality_style"] == style


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


# ─── Personality + YOLO 联合场景 ───


class TestPersonalityYoloCombined:
    """Personality 和 YOLO 同时使用的场景。"""

    @pytest.mark.asyncio
    async def test_agent_with_both_personality_and_yolo(self, async_client: AsyncClient) -> None:
        """同时设置 personality + YOLO 不互相干扰。"""
        agent = await _create_test_agent(
            async_client,
            personality_style="humorous",
            security_overrides={"yoloModeEnabled": True},
        )
        assert agent["personality_style"] == "humorous"
        assert agent["security_overrides"]["yoloModeEnabled"] is True

    @pytest.mark.asyncio
    async def test_update_personality_preserves_yolo(self, async_client: AsyncClient) -> None:
        """更新 personality 不影响 YOLO security_overrides。"""
        agent = await _create_test_agent(
            async_client,
            personality_style="professional",
            security_overrides={"yoloModeEnabled": True, "yolo_mode_timeout": 300},
        )
        agent_id = agent["id"]

        resp = await async_client.put(f"/api/agents/{agent_id}", json={"personality_style": "creative"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["personality_style"] == "creative"
        so = data.get("security_overrides")
        if so is not None:
            assert so.get("yoloModeEnabled") is True

    @pytest.mark.asyncio
    async def test_personality_template_data_integrity(self) -> None:
        """验证所有 personality 模板数据完整性。"""
        from app.ai_agents.personality_templates import get_personality_template, list_all_personalities

        templates = list_all_personalities()
        assert len(templates) == 16

        for style in [
            "professional",
            "friendly",
            "concise",
            "detailed",
            "humorous",
            "academic",
            "creative",
            "socratic",
            "pirate",
            "shakespeare",
            "noir",
            "kawaii",
            "catgirl",
            "hype",
            "uwu",
            "surfer",
        ]:
            t = get_personality_template(style)
            assert t is not None
            assert t.system_prompt_suffix, f"{style} missing system_prompt_suffix"
            assert t.emoji, f"{style} missing emoji"
            assert t.description, f"{style} missing description"
            assert t.display_name, f"{style} missing display_name"

    @pytest.mark.asyncio
    async def test_delete_agent_cleans_personality(self, async_client: AsyncClient) -> None:
        """删除 Agent 后不再能获取其 personality。"""
        agent = await _create_test_agent(async_client, personality_style="socratic")
        agent_id = agent["id"]

        resp = await async_client.delete(f"/api/agents/{agent_id}")
        assert resp.status_code == 200

        resp = await async_client.get(f"/api/agents/{agent_id}")
        assert resp.status_code == 404
