"""RevertFiles Chrome E2E test fixture — seed chat + snapshot data.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定)
app.services.agent.agent_service::AgentService (POS: 智能体列表)
app.services.chat.chat_service::ChatService (POS: 会话与消息持久化)
myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer (POS: 文件快照)

[OUTPUT]
seed_revert_fixture: POST /test/seed-revert-fixture

[POS]
RevertFiles E2E fixture. Seeds DB + workspace snapshot for variant-based revert testing.
"""

from __future__ import annotations

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

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.params.workspace_resolve import (
    resolve_default_chat_workspace_dir,
)
from app.services.chat.chat_service import ChatService

router = APIRouter()

_REVERT_FIXTURE_FILE = "revert_e2e_fixture.txt"
_REVERT_FIXTURE_BEFORE = "revert fixture before\n"
_REVERT_FIXTURE_AFTER = "revert fixture after\n"

_VALID_VARIANTS = frozenset({"modify", "create", "empty", "session", "large_skip"})


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
    if normalized not in _VALID_VARIANTS:
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
        chat_id, "user", "Revert E2E fixture question", now, timezone,
    )
    await ChatService.append_message(
        chat_id, "assistant", "Revert E2E fixture answer with file change.",
        now, timezone, message_id=message_id,
    )
    if normalized == "session":
        await ChatService.append_message(
            chat_id, "user", "Revert E2E fixture follow-up", now, timezone,
        )
        await ChatService.append_message(
            chat_id, "assistant", "Revert E2E fixture second answer with file change.",
            now, timezone, message_id=message_ids[1],
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
