"""Local-only workspace merge Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)

[OUTPUT]
seed_workspace_merge_fixture: persisted workspaceMergeFailures for Chrome E2E (variant=batch_merge_fail)

[POS]
Split from test_fixtures.py for line-budget compliance; mounted via test_fixtures router include.
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

_MERGE_FIXTURE_ANSWER = "Workspace merge E2E fixture answer."
_MERGE_FIXTURE_ERROR = "task_index=1: No space left on device"


@router.post("/test/seed-workspace-merge-fixture", include_in_schema=False)
async def seed_workspace_merge_fixture(
    variant: str = "batch_merge_fail",
) -> dict[str, str]:
    """Local dev/test only: seed chat with persisted workspaceMergeFailures for Chrome E2E.

    variant:
      - batch_merge_fail (default): assistant message includes ISOLATED_COPY merge failure metadata
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in {"batch_merge_fail"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported workspace-merge fixture variant: {variant}",
        )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for workspace-merge E2E seed",
        )

    agent = agents[0]
    chat_id = f"e2ewsmr{uuid4().hex[:8]}"
    message_id = str(uuid4())

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Workspace merge Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        "Workspace merge E2E fixture question",
        now,
        timezone,
    )

    extra_data: dict[str, object] = {
        "workspaceMergeFailures": [{"message": _MERGE_FIXTURE_ERROR}],
        "workspaceMergeFailedCount": 1,
        "completionStatus": "warning",
    }
    await ChatService.append_message(
        chat_id,
        "assistant",
        _MERGE_FIXTURE_ANSWER,
        now,
        timezone,
        message_id=message_id,
        extra_data=extra_data,
    )

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "ui_path": f"/{chat_id}",
        "variant": normalized,
        "merge_error": _MERGE_FIXTURE_ERROR,
    }
