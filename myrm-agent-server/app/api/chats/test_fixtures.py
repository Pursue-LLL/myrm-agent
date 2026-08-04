"""Local-only HTTP fixtures for Chrome MCP E2E tests.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
app.services.agent.agent_service::AgentService (POS: 智能体列表，选取 E2E seed 关联 agent)
app.services.chat.chat_service::ChatService (POS: 会话与消息持久化)
app.services.kanban.KanbanService (POS: 看板/任务持久化，Kanban closure seed)
myrm_agent_harness.toolkits.kanban.types (POS: TaskPriority/TaskStatus/source_chat metadata SSOT)

[OUTPUT]
seed_citation_fixture: 创建带 citedMemoryIds 的 assistant 消息 + wiki settings 深链参数
seed_skill_chip_transcript_fixture: 创建带 `[use skill]` wire 前缀的用户消息（Skill chip Chrome E2E）
seed_skill_chip_composer_fixture: 创建绑定 systematic-debugging 的空会话（Slash chip composer Chrome E2E）
seed_embed_fixture: 创建带 YouTube markdown 链接的 assistant 消息（Link Embeds Chrome E2E）
seed_kanban_closure_fixture: 创建 Kanban 看板/任务 + Chat 内 kanban_tasks_created 卡片数据
seed_deliverable_link_fixture: 见 test_fixtures_deliverable.py（workspace 文件 + inline deliverable markdown）
seed_copilot_fixture: 见 test_fixtures_copilot.py（assistant markdown + active run digest，Lean Co-Pilot Chrome E2E）

[POS]
Chats API 本地测试 fixture。为 Wiki citation / Kanban closure Chrome E2E 提供可重复、无 LLM 的 DB 与 workspace 种子数据。
RevertFiles fixture 见 test_fixtures_revert.py。
clarify refresh / file_edit batch / UECD evicted seed 见子模块 test_fixtures_*（子路由挂载）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.kanban.types import (
    KANBAN_SOURCE_CHAT_METADATA_KEY,
    TaskPriority,
    TaskStatus,
)

from app.config.deploy_mode import is_local_mode
from app.database.dto import AgentCreate, ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.services.kanban import KanbanService

from .test_fixtures_allowed_tools_recovery import (
    router as allowed_tools_recovery_fixture_router,
)
from .test_fixtures_clarify_refresh import router as clarify_refresh_fixture_router
from .test_fixtures_copilot import router as copilot_fixture_router
from .test_fixtures_context_retention import (
    router as context_retention_fixture_router,
)
from .test_fixtures_deliverable import router as deliverable_fixture_router
from .test_fixtures_evicted import router as evicted_fixture_router
from .test_fixtures_file_edit_batch import router as file_edit_batch_fixture_router
from .test_fixtures_file_mutation import router as file_mutation_fixture_router
from .test_fixtures_workspace_merge import router as workspace_merge_fixture_router
from .test_fixtures_guardrail_bash import router as guardrail_bash_fixture_router
from .test_fixtures_revert import router as revert_fixture_router
from .test_fixtures_stream_retry_busy import router as stream_retry_busy_fixture_router

router = APIRouter()

_CITATION_COUNT = 10
_EMBED_YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_EMBED_ASSISTANT_MARKDOWN = (
    f"Link embed E2E fixture — watch [YouTube video]({_EMBED_YOUTUBE_URL})."
)


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
        raise HTTPException(
            status_code=500, detail="No agents available for citation E2E seed"
        )

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
        raise HTTPException(
            status_code=500, detail="No agents available for skill chip E2E seed"
        )

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
        raise HTTPException(
            status_code=500, detail="No agents available for embed E2E seed"
        )

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


@router.post("/test/seed-kanban-closure-fixture", include_in_schema=False)
async def seed_kanban_closure_fixture() -> dict[str, str]:
    """Local dev/test only: seed chat KanbanTaskCreatedCard + board task for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500, detail="No agents available for kanban closure E2E seed"
        )

    agent = agents[0]
    agent_id = agent.id

    chat_id = f"e2ekanban{uuid4().hex[:8]}"
    marker = uuid4().hex[:8]
    board_name = f"Kanban closure E2E {marker}"
    task_title = f"Closure task {marker}"

    kanban = KanbanService.get_instance()
    board = await kanban.create_board(
        board_name, description="Kanban Chat↔Board closure Chrome E2E"
    )
    task = await kanban.add_task(
        board.board_id,
        task_title,
        priority=TaskPriority.LOW,
        initial_status=TaskStatus.READY,
        metadata_patch={KANBAN_SOURCE_CHAT_METADATA_KEY: chat_id},
    )

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Kanban closure Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    kanban_card_extra: dict[str, object] = {
        "kanban_tasks_created": [
            {
                "task_id": task.task_id,
                "title": task_title,
                "board_id": board.board_id,
            }
        ],
    }

    await ChatService.append_message(
        chat_id,
        "user",
        "Kanban closure E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        "Kanban closure E2E fixture answer with task created card.",
        now,
        timezone,
        extra_data=kanban_card_extra,
    )

    board_deep_link_path = (
        f"/settings/kanban?source_chat={chat_id}&board_id={board.board_id}"
    )

    return {
        "chat_id": chat_id,
        "board_id": board.board_id,
        "task_id": task.task_id,
        "task_title": task_title,
        "ui_path": f"/{chat_id}",
        "board_deep_link_path": board_deep_link_path,
    }


router.include_router(deliverable_fixture_router)
router.include_router(copilot_fixture_router)
router.include_router(clarify_refresh_fixture_router)
router.include_router(file_edit_batch_fixture_router)
router.include_router(file_mutation_fixture_router)
router.include_router(workspace_merge_fixture_router)
router.include_router(evicted_fixture_router)
router.include_router(revert_fixture_router)
router.include_router(stream_retry_busy_fixture_router)
router.include_router(allowed_tools_recovery_fixture_router)
router.include_router(guardrail_bash_fixture_router)
router.include_router(context_retention_fixture_router)
