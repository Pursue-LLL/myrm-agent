"""Local-only HTTP fixtures — inline core seed endpoints.

Four seed endpoints that stay adjacent to the package aggregator: citation,
skill chip transcript, skill chip composer and link embed. All are
local/tauri-only via the ``is_local_mode`` guard.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
app.services.agent.agent_service::AgentService (POS: 智能体列表/创建，选取 E2E seed 关联 agent)
app.services.chat.chat_service::ChatService (POS: 会话与消息持久化)

[OUTPUT]
seed_citation_fixture: 创建带 citedMemoryIds 的 assistant 消息 + wiki settings 深链参数
seed_skill_chip_transcript_fixture: 创建带 `[use skill]` wire 前缀的用户消息（Skill chip Chrome E2E）
seed_skill_chip_composer_fixture: 创建绑定 systematic-debugging 的空会话（Slash chip composer Chrome E2E）
seed_embed_fixture: 创建带 YouTube markdown 链接的 assistant 消息（Link Embeds Chrome E2E）

[POS]
Chats API 本地测试 fixture 子包的内联核心 seed 端点集合。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import AgentCreate, ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_CITATION_COUNT = 10
_EMBED_YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_EMBED_ASSISTANT_MARKDOWN = f"Link embed E2E fixture — watch [YouTube video]({_EMBED_YOUTUBE_URL})."


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


_SKILL_CHIP_WIRE_SKILL = "systematic-debugging"
_SKILL_CHIP_USER_TEXT = "analyze this bug"


@router.post("/test/seed-skill-chip-transcript-fixture", include_in_schema=False)
async def seed_skill_chip_transcript_fixture() -> dict[str, str]:
    """Local dev/test only: seed user message with explicit skill wire prefix for chip Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for skill chip E2E seed")

    agent = agents[0]
    agent_id = agent.id

    chat_id = f"e2eskillchip{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Skill chip Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    wire_content = f"[use {_SKILL_CHIP_WIRE_SKILL}] {_SKILL_CHIP_USER_TEXT}"

    await ChatService.append_message(
        chat_id,
        "user",
        wire_content,
        now,
        timezone,
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent_id,
        "skill_name": _SKILL_CHIP_WIRE_SKILL,
        "user_text": _SKILL_CHIP_USER_TEXT,
        "wire_content": wire_content,
        "ui_path": f"/{chat_id}",
    }


@router.post("/test/seed-skill-chip-composer-fixture", include_in_schema=False)
async def seed_skill_chip_composer_fixture() -> dict[str, str]:
    """Local dev/test only: seed empty chat bound to agent with systematic-debugging skill."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    suffix = uuid4().hex[:8]
    agent = await AgentService.create_agent(
        AgentCreate.model_validate(
            {
                "name": f"Slash Skill Chip Composer E2E {suffix}",
                "description": "Chrome READ E2E for slash skill chip composer UX",
                "system_prompt": "You are a test agent.",
                "mcp_ids": [],
                "skill_ids": [_SKILL_CHIP_WIRE_SKILL],
            }
        )
    )
    agent_id = agent.id

    chat_id = f"e2eslashchip{uuid4().hex[:10]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Slash skill chip composer Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent_id,
        "skill_id": _SKILL_CHIP_WIRE_SKILL,
        "ui_path": f"/{chat_id}?agentId={agent_id}",
    }


@router.post("/test/seed-embed-fixture", include_in_schema=False)
async def seed_embed_fixture() -> dict[str, str]:
    """Local dev/test only: seed assistant markdown with YouTube link for Link Embeds Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for embed E2E seed")

    agent = agents[0]
    agent_id = agent.id

    chat_id = f"e2eembed{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Link embed Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"

    await ChatService.append_message(
        chat_id,
        "user",
        "Link embed E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        _EMBED_ASSISTANT_MARKDOWN,
        now,
        timezone,
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent_id,
        "youtube_url": _EMBED_YOUTUBE_URL,
        "ui_path": f"/{chat_id}",
    }
