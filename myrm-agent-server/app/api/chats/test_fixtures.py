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
seed_revert_fixture: 创建 RevertFiles E2E 数据（variant=modify|create|empty|session|large_skip）

[POS]
Chats API 本地测试 fixture。为 Wiki citation / Kanban closure / RevertFiles Chrome E2E 提供可重复、无 LLM 的 DB 与 workspace 种子数据。
clarify refresh / file_edit batch / UECD evicted seed 见子模块 test_fixtures_*（子路由挂载）。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    FileSnapshot,
    SnapshotOp,
    SnapshotSkipReason,
    SnapshotStore,
)
from myrm_agent_harness.toolkits.kanban.types import (
    KANBAN_SOURCE_CHAT_METADATA_KEY,
    TaskPriority,
    TaskStatus,
)

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.params.workspace_resolve import (
    resolve_default_chat_workspace_dir,
)
from app.services.chat.chat_service import ChatService
from app.services.kanban import KanbanService

router = APIRouter()

_REVERT_FIXTURE_FILE = "revert_e2e_fixture.txt"
_REVERT_FIXTURE_BEFORE = "revert fixture before\n"
_REVERT_FIXTURE_AFTER = "revert fixture after\n"

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


@router.post("/test/seed-revert-fixture", include_in_schema=False)
async def seed_revert_fixture(variant: str = "modify") -> dict[str, str | list[str]]:
    """Local dev/test only: seed chat message + optional on-disk file snapshot for RevertFiles E2E.

    variant:
      - modify (default): one MODIFY snapshot + changed file on disk
      - create: one CREATE snapshot (revert deletes the new file)
      - empty: assistant message without snapshots (empty-changes UX)
      - session: two messages each with MODIFY snapshots (session-level revert)
      - large_skip: MODIFY skipped (file too large) — Honest UX non-revertible toast
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in {"modify", "create", "empty", "session", "large_skip"}:
        raise HTTPException(
            status_code=400, detail=f"Unsupported revert fixture variant: {variant}"
        )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500, detail="No agents available for revert E2E seed"
        )

    agent = agents[0]
    agent_id = agent.id
    chat_id = f"e2erevert{uuid4().hex[:8]}"
    message_id = str(uuid4())

    workspace_dir = await resolve_default_chat_workspace_dir(
        chat_id, persist_workspace=True
    )
    if not workspace_dir and normalized != "empty":
        raise HTTPException(
            status_code=500, detail="Failed to resolve workspace for revert E2E seed"
        )

    file_path = str(Path(workspace_dir) / _REVERT_FIXTURE_FILE) if workspace_dir else ""
    message_ids: list[str] = [message_id]

    if normalized in {"modify", "create", "session", "large_skip"}:
        assert workspace_dir is not None
        SnapshotStore.reset()
        store = SnapshotStore.get()

        if normalized == "modify":
            Path(file_path).write_text(_REVERT_FIXTURE_AFTER, encoding="utf-8")
            snapshot = FileSnapshot(
                path=file_path,
                operation=SnapshotOp.MODIFY,
                original_content=_REVERT_FIXTURE_BEFORE,
            )
            store.record(chat_id, message_id, snapshot)
            await store.persist_to_disk(workspace_dir, chat_id, message_id)
        elif normalized == "large_skip":
            large_content = "x" * (2 * 1024 * 1024 + 128)
            Path(file_path).write_text(large_content, encoding="utf-8")
            store.record_skipped(
                chat_id,
                message_id,
                file_path,
                SnapshotOp.MODIFY,
                SnapshotSkipReason.FILE_TOO_LARGE,
            )
            await store.persist_to_disk(workspace_dir, chat_id, message_id)
        elif normalized == "create":
            Path(file_path).write_text(_REVERT_FIXTURE_AFTER, encoding="utf-8")
            snapshot = FileSnapshot(
                path=file_path,
                operation=SnapshotOp.CREATE,
                original_content=None,
            )
            store.record(chat_id, message_id, snapshot)
            await store.persist_to_disk(workspace_dir, chat_id, message_id)
        else:
            file_b = str(Path(workspace_dir) / "revert_e2e_fixture_b.txt")
            Path(file_path).write_text(_REVERT_FIXTURE_AFTER, encoding="utf-8")
            Path(file_b).write_text("file b after\n", encoding="utf-8")
            snap_a = FileSnapshot(
                path=file_path,
                operation=SnapshotOp.MODIFY,
                original_content=_REVERT_FIXTURE_BEFORE,
            )
            snap_b = FileSnapshot(
                path=file_b,
                operation=SnapshotOp.MODIFY,
                original_content="file b before\n",
            )
            store.record(chat_id, message_id, snap_a)
            await store.persist_to_disk(workspace_dir, chat_id, message_id)

            message_id_b = str(uuid4())
            message_ids.append(message_id_b)
            store.record(chat_id, message_id_b, snap_b)
            await store.persist_to_disk(workspace_dir, chat_id, message_id_b)

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="RevertFiles Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        "Revert E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        "Revert E2E fixture answer with file change.",
        now,
        timezone,
        message_id=message_id,
    )
    if normalized == "session":
        await ChatService.append_message(
            chat_id,
            "user",
            "Revert E2E fixture follow-up",
            now,
            timezone,
        )
        await ChatService.append_message(
            chat_id,
            "assistant",
            "Revert E2E fixture second answer with file change.",
            now,
            timezone,
            message_id=message_ids[1],
        )

    payload: dict[str, str | list[str]] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "ui_path": f"/{chat_id}",
        "variant": normalized,
    }
    if file_path:
        payload["file_path"] = file_path
    if len(message_ids) > 1:
        payload["message_ids"] = message_ids
    if normalized == "session" and workspace_dir:
        payload["file_path_b"] = str(Path(workspace_dir) / "revert_e2e_fixture_b.txt")
    return payload


from .test_fixtures_clarify_refresh import router as clarify_refresh_fixture_router
from .test_fixtures_evicted import router as evicted_fixture_router
from .test_fixtures_file_edit_batch import router as file_edit_batch_fixture_router

router.include_router(clarify_refresh_fixture_router)
router.include_router(file_edit_batch_fixture_router)
router.include_router(evicted_fixture_router)
