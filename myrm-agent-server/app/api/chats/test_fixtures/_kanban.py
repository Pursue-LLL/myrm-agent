"""Local-only HTTP fixtures — Kanban seed endpoints.

Kanban closure (chat `kanban_tasks_created` card + board task) and Kanban
IN_REVIEW (Fleet pendingApprovals KPI) seeds. Both are local/tauri-only via
the ``is_local_mode`` guard.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
app.services.agent.agent_service::AgentService (POS: 智能体列表，选取 E2E seed 关联 agent)
app.services.chat.chat_service::ChatService (POS: 会话与消息持久化)
app.services.kanban.KanbanService (POS: 看板/任务持久化)
myrm_agent_harness.toolkits.kanban.types (POS: TaskPriority/TaskStatus/source_chat metadata SSOT)

[OUTPUT]
seed_kanban_closure_fixture: 创建 Kanban 看板/任务 + Chat 内 kanban_tasks_created 卡片数据
seed_kanban_in_review_fixture: 创建 IN_REVIEW 看板任务（Fleet pendingApprovals KPI Chrome E2E；task 绑定内置 agent 供抽屉本地化断言）

[POS]
Chats API 本地测试 fixture 子包的 Kanban seed 端点集合。
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


@router.post("/test/seed-kanban-in-review-fixture", include_in_schema=False)
async def seed_kanban_in_review_fixture() -> dict[str, str]:
    """Local dev/test only: seed a board task in IN_REVIEW state for Chrome E2E.

    The IN_REVIEW state is only reachable after a real agent completes a
    require_approval run, which an E2E probe cannot dispatch. Instead of
    writing the SQLite file directly (a second writer corrupts the server's
    WAL), this fixture drives the same KanbanService/store the HTTP layer
    uses — the backend remains the single writer.
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    marker = uuid4().hex[:8]
    board_name = f"Kanban IN_REVIEW E2E {marker}"
    task_title = f"IN_REVIEW task {marker}"

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for kanban in-review E2E seed")
    agent = next(
        (a for a in agents if a.id == "builtin-general"),
        agents[0],
    )
    agent_id = agent.id

    kanban = KanbanService.get_instance()
    board = await kanban.create_board(board_name, description="Kanban IN_REVIEW Fleet KPI Chrome E2E")
    task = await kanban.add_task(
        board.board_id,
        task_title,
        priority=TaskPriority.NORMAL,
        require_approval=True,
        agent_id=agent_id,
    )
    moved = await kanban.store.transition_task_status(task.task_id, TaskStatus.READY, TaskStatus.IN_REVIEW)
    if moved is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to move task {task.task_id} to IN_REVIEW",
        )

    return {
        "board_id": board.board_id,
        "task_id": task.task_id,
        "task_title": task_title,
        "board_name": board_name,
        "agent_id": agent_id,
    }
