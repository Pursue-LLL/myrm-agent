"""Local-only HTTP fixtures for Chrome MCP E2E tests.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
app.services.agent.agent_service::AgentService (POS: 智能体列表，选取 E2E seed 关联 agent)
app.services.chat.chat_service::ChatService (POS: 会话与消息持久化)
app.services.kanban.KanbanService (POS: 看板/任务持久化，Kanban closure seed)
myrm_agent_harness.toolkits.kanban.types (POS: TaskPriority/TaskStatus/source_chat metadata SSOT)

[OUTPUT]
seed_citation_fixture: 创建带 citedMemoryIds 的 assistant 消息 + wiki settings 深链参数
seed_kanban_closure_fixture: 创建 Kanban 看板/任务 + Chat 内 kanban_tasks_created 卡片数据

[POS]
Chats API 本地测试 fixture。为 Wiki citation / Kanban Chat↔Board closure Chrome E2E 提供可重复、无 LLM 的 DB 种子数据。
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
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.services.kanban import KanbanService

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


@router.post("/test/seed-kanban-closure-fixture", include_in_schema=False)
async def seed_kanban_closure_fixture() -> dict[str, str]:
    """Local dev/test only: seed chat KanbanTaskCreatedCard + board task for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for kanban closure E2E seed")

    agent = agents[0]
    agent_id = agent.id

    chat_id = f"e2ekanban{uuid4().hex[:8]}"
    marker = uuid4().hex[:8]
    board_name = f"Kanban closure E2E {marker}"
    task_title = f"Closure task {marker}"

    kanban = KanbanService.get_instance()
    board = await kanban.create_board(board_name, description="Kanban Chat↔Board closure Chrome E2E")
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

    board_deep_link_path = f"/settings/kanban?source_chat={chat_id}&board_id={board.board_id}"

    return {
        "chat_id": chat_id,
        "board_id": board.board_id,
        "task_id": task.task_id,
        "task_title": task_title,
        "ui_path": f"/{chat_id}",
        "board_deep_link_path": board_deep_link_path,
    }
