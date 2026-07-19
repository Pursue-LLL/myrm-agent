"""Local-only HTTP fixtures for Chrome MCP E2E tests.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
app.services.agent.agent_service::AgentService (POS: 智能体列表，选取 wiki 深链 scope)
app.services.chat.chat_service::ChatService (POS: 会话与消息持久化)

[OUTPUT]
seed_citation_fixture: 创建带 citedMemoryIds 的 assistant 消息 + wiki settings 深链参数

[POS]
Chats API 本地测试 fixture。为 Wiki citation Chrome E2E 提供可重复、无 LLM 的 DB 种子数据。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_CITATION_COUNT = 10


def _build_citation_extra_data() -> dict[str, object]:
    cited_ids = [f"e2e-cite-{index}" for index in range(1, _CITATION_COUNT + 1)]
    cited_refs: list[dict[str, object]] = [
        {
            "id": memory_id,
            "memory_type": "semantic",
            "content": f"E2E citation fixture {memory_id}",
            "score": 0.9,
            "primary_namespace": "global",
            "namespaces": ["global"],
        }
        for memory_id in cited_ids
    ]
    return {
        "citedMemoryIds": cited_ids,
        "citedMemoryRefs": cited_refs,
    }


@router.post("/test/seed-citation-fixture", include_in_schema=False)
async def seed_citation_fixture() -> dict[str, str | int]:
    """Local dev/test only: seed a chat with persisted memory citations for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for citation E2E seed")

    agent = agents[0]
    agent_id = agent.id
    agent_name = agent.display_name or agent.id

    chat_id = f"e2ewiki{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Wiki citation Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"

    await ChatService.append_message(
        chat_id,
        "user",
        "Wiki citation E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        "Wiki citation E2E fixture answer with recalled memories.",
        now,
        timezone,
        extra_data=_build_citation_extra_data(),
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "citation_count": _CITATION_COUNT,
        "ui_path": f"/{chat_id}",
        "wiki_settings_path": f"/settings/wiki?agentId={agent_id}",
    }
