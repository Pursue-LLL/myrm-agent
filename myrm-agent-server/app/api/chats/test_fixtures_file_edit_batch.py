"""Local-only file_edit batch Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)
app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: workspace path)
myrm_agent_harness.agent.streaming.step_builder::build_step_data (POS: progressSteps diff items)

[OUTPUT]
seed_file_edit_batch_fixture: batch file_edit E2E（variant=live|read_ui）
seed_file_edit_batch_workspace: 向已有 chat workspace 写入 batch_edit_e2e.txt

[POS]
Split from test_fixtures.py for line-budget compliance; mounted via test_fixtures router include.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.params.workspace_resolve import (
    resolve_default_chat_workspace_dir,
)
from app.services.chat.chat_service import ChatService

router = APIRouter()

_BATCH_EDIT_FIXTURE_FILE = "batch_edit_e2e.txt"
_BATCH_EDIT_FIXTURE_CONTENT = "line_a\nline_b\nline_c\n"
_BATCH_EDIT_FIXTURE_ANSWER = "Batch file edit E2E fixture answer."


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
        extra_data: dict[str, object] = {
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
