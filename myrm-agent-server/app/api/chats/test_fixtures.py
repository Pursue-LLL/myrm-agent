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
seed_evicted_live_terminal_fixture: UECD web_fetch spill + LiveTerminal progressSteps（Chrome/API E2E）
seed_file_edit_batch_fixture: batch file_edit E2E（variant=live|read_ui；workspace 文件 + 可选 progressSteps）
seed_file_edit_batch_workspace: 向已有 chat workspace 写入 batch_edit_e2e.txt（Chrome LIVE 预写）

[POS]
Chats API 本地测试 fixture。为 Wiki citation / Kanban closure / RevertFiles / file_edit batch Chrome E2E 提供可重复、无 LLM 的 DB 与 workspace 种子数据。
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

_BATCH_EDIT_FIXTURE_FILE = "batch_edit_e2e.txt"
_BATCH_EDIT_FIXTURE_CONTENT = "line_a\nline_b\nline_c\n"
_BATCH_EDIT_FIXTURE_ANSWER = "Batch file edit E2E fixture answer."

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


@router.post("/test/seed-file-edit-batch-fixture", include_in_schema=False)
async def seed_file_edit_batch_fixture(
    variant: str = "live",
    agent_id: str | None = None,
) -> dict[str, str]:
    """Local dev/test only: seed workspace file + chat for file_edit batch Chrome E2E.

    variant:
      - live (default): user message only; file on disk for LIVE_AGENT edit flow
      - read_ui: assistant message includes persisted batch file_edit progressSteps
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in {"live", "read_ui"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file-edit batch fixture variant: {variant}",
        )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500, detail="No agents available for file-edit batch E2E seed"
        )

    agent = agents[0]
    resolved_agent_id = (agent_id or "").strip() or agent.id
    chat_id = f"e2efedit{uuid4().hex[:8]}"
    message_id = str(uuid4())

    workspace_dir = await resolve_default_chat_workspace_dir(
        chat_id, persist_workspace=True
    )
    if not workspace_dir:
        raise HTTPException(
            status_code=500, detail="Failed to resolve workspace for file-edit batch E2E seed"
        )

    rel_path = _BATCH_EDIT_FIXTURE_FILE
    file_path = str(Path(workspace_dir) / rel_path)
    Path(file_path).write_text(_BATCH_EDIT_FIXTURE_CONTENT, encoding="utf-8")

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="File edit batch Chrome E2E",
            agent_id=resolved_agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        "Batch file edit E2E fixture question",
        now,
        timezone,
    )

    extra_data: dict[str, object] | None = None
    if normalized == "read_ui":
        from myrm_agent_harness.agent.streaming.step_builder import build_step_data

        built = build_step_data(
            "file_edit_tool",
            {
                "path": rel_path,
                "edits": [
                    {"old_str": "line_a", "new_str": "LINE_A"},
                    {"old_str": "line_c", "new_str": "LINE_C"},
                ],
            },
        )
        extra_data = {
            "progressSteps": [
                {
                    "step_key": built.get("step_key", "file_edit_tool"),
                    "tool_name": "file_edit_tool",
                    "items": built.get("data", []),
                }
            ]
        }
        await ChatService.append_message(
            chat_id,
            "assistant",
            _BATCH_EDIT_FIXTURE_ANSWER,
            now,
            timezone,
            message_id=message_id,
            extra_data=extra_data,
        )

    return {
        "chat_id": chat_id,
        "message_id": message_id if normalized == "read_ui" else "",
        "ui_path": f"/{chat_id}",
        "file_path": file_path,
        "rel_path": rel_path,
        "variant": normalized,
        "agent_id": resolved_agent_id,
    }


@router.post("/test/seed-file-edit-batch-workspace", include_in_schema=False)
async def seed_file_edit_batch_workspace(chat_id: str) -> dict[str, str]:
    """Local dev/test only: write batch_edit_e2e.txt into an existing chat workspace."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    resolved_chat_id = chat_id.strip()
    if not resolved_chat_id:
        raise HTTPException(status_code=400, detail="chat_id required")

    workspace_dir = await resolve_default_chat_workspace_dir(
        resolved_chat_id, persist_workspace=True
    )
    if not workspace_dir:
        raise HTTPException(
            status_code=500,
            detail="Failed to resolve workspace for file-edit batch workspace seed",
        )

    rel_path = _BATCH_EDIT_FIXTURE_FILE
    file_path = str(Path(workspace_dir) / rel_path)
    Path(file_path).write_text(_BATCH_EDIT_FIXTURE_CONTENT, encoding="utf-8")

    return {
        "chat_id": resolved_chat_id,
        "file_path": file_path,
        "rel_path": rel_path,
    }


_UECD_E2E_LINE_COUNT = 120
_UECD_E2E_MARKER_LINE = 42


def _resolve_evicted_write_roots(workspace_dir: str) -> list[Path]:
    """Match live server evicted path resolution (MYRM_WORKSPACE_ROOT + harness defaults)."""
    roots: list[Path] = [Path(workspace_dir)]
    workspace_env = os.environ.get("MYRM_WORKSPACE_ROOT")
    if workspace_env:
        candidate = Path(workspace_env).expanduser()
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    if is_local_mode():
        default = Path.home() / ".myrm" / "workspace"
        if default.is_dir() and default not in roots:
            roots.append(default)
    return roots


@router.post("/test/seed-evicted-live-terminal-fixture", include_in_schema=False)
async def seed_evicted_live_terminal_fixture(
    variant: str = "full",
) -> dict[str, str | int]:
    """Local dev/test only: seed UECD web_fetch spill file + LiveTerminal progressSteps.

    variant:
      - full (default): write spill file to all server-visible roots
      - expired: same as full, then delete spill files (drawer expired UX)
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in {"full", "expired"}:
        raise HTTPException(status_code=400, detail=f"Unsupported evicted fixture variant: {variant}")

    from myrm_agent_harness.agent.context_management.infra.evicted_content import (
        build_evicted_basename,
    )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500, detail="No agents available for evicted live terminal E2E seed"
        )

    agent = agents[0]
    chat_id = f"e2euecd{uuid4().hex[:8]}"
    message_id = str(uuid4())
    filename = build_evicted_basename("web_fetch", ext="md")
    content = "".join(
        f"MYRM_E2E_UECD_SPILL_LINE_{index}\n" for index in range(_UECD_E2E_LINE_COUNT)
    )

    workspace_dir = await resolve_default_chat_workspace_dir(
        chat_id, persist_workspace=True
    )
    if not workspace_dir:
        raise HTTPException(
            status_code=500,
            detail="Failed to resolve workspace for evicted live terminal E2E seed",
        )

    write_roots = _resolve_evicted_write_roots(workspace_dir)
    for root in write_roots:
        evicted_dir = root / ".context" / chat_id / "evicted"
        evicted_dir.mkdir(parents=True, exist_ok=True)
        (evicted_dir / filename).write_text(content, encoding="utf-8")

    if normalized == "expired":
        for root in write_roots:
            spill_path = root / ".context" / chat_id / "evicted" / filename
            if spill_path.is_file():
                spill_path.unlink()

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="UECD LiveTerminal Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    preview_stdout = (
        "[LARGE OUTPUT TRUNCATED (120 lines, ~500 tokens)]\n\n"
        + content[:800]
        + "\n\n[Truncated: showing head/tail preview only]"
    )
    extra_data: dict[str, object] = {
        "progressSteps": [
            {
                "step_key": "web_fetch_tool",
                "tool_name": "web_fetch_tool",
                "stdout": preview_stdout,
                "evicted_file_ref": filename,
                "status": "success",
            }
        ]
    }

    await ChatService.append_message(
        chat_id,
        "user",
        "UECD evicted output E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        "UECD evicted output E2E fixture answer.",
        now,
        timezone,
        message_id=message_id,
        extra_data=extra_data,
    )

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "filename": filename,
        "ui_path": f"/{chat_id}",
        "marker_line": f"MYRM_E2E_UECD_SPILL_LINE_{_UECD_E2E_MARKER_LINE}",
        "line_count": _UECD_E2E_LINE_COUNT,
        "agent_id": agent.id,
        "workspace_dir": workspace_dir,
        "variant": normalized,
    }
