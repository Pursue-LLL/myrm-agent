"""Local-only HTTP fixture: agent-bound chats for SecurityPreset Chrome E2E.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
app.database.dto::AgentCreate / ChatCreate (POS: 创建 DTO)
app.services.agent.agent_service::AgentService (POS: 智能体创建)
app.services.chat.chat_service::ChatService (POS: 会话创建)

[OUTPUT]
seed_security_preset_fixture: 创建「带 default_security_preset 的 Agent + 绑定 Chat」与
「无 default 的 Agent + 绑定 Chat」，返回 ui_path（?agentId=）供 Chrome E2E 断言
会话级安全预设的初始化 / UI 切换 / hitl 回落。

[POS]
Chats API 本地测试 fixture 子模块（test_fixtures.py include 挂载）。
SecurityPreset 生命周期（绑定/切换/重置）的 E2E 种子，复用 seed_citation_fixture 的
「创建 agent → 绑定 chat → 返回 ui_path」模式，零业务逻辑、无 LLM。
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import AgentCreate, ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()


@router.post("/test/seed-security-preset-fixture", include_in_schema=False)
async def seed_security_preset_fixture() -> dict[str, str]:
    """Local dev/test only: seed two agent-bound chats for SecurityPreset Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    preset_agent = await AgentService.create_agent(
        AgentCreate.model_validate(
            {
                "name": f"SecurityPreset E2E accept_edits {uuid4().hex[:8]}",
                "description": "Chrome E2E: default_security_preset=accept_edits agent",
                "system_prompt": "You are a test agent.",
                "mcp_ids": [],
                "default_security_preset": "accept_edits",
            }
        )
    )

    plain_agent = await AgentService.create_agent(
        AgentCreate.model_validate(
            {
                "name": f"SecurityPreset E2E plain {uuid4().hex[:8]}",
                "description": "Chrome E2E: agent without default_security_preset",
                "system_prompt": "You are a test agent.",
                "mcp_ids": [],
            }
        )
    )

    preset_chat_id = f"e2esecpreset{uuid4().hex[:8]}"
    plain_chat_id = f"e2esecpreset{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=preset_chat_id,
            title="SecurityPreset accept_edits Chrome E2E",
            agent_id=preset_agent.id,
            action_mode="agent",
            messages=[],
        ),
    )
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=plain_chat_id,
            title="SecurityPreset plain Chrome E2E",
            agent_id=plain_agent.id,
            action_mode="agent",
            messages=[],
        ),
    )

    return {
        "preset_chat_id": preset_chat_id,
        "preset_agent_id": preset_agent.id,
        "preset_ui_path": f"/?agentId={preset_agent.id}",
        "plain_chat_id": plain_chat_id,
        "plain_agent_id": plain_agent.id,
        "plain_ui_path": f"/?agentId={plain_agent.id}",
    }
