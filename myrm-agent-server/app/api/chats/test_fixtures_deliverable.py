"""Local-only deliverable link Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: workspace path)

[OUTPUT]
seed_deliverable_link_fixture: workspace file + assistant markdown with workspace/ inline deliverable

[POS]
Mounted via test_fixtures router include.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.params.workspace_resolve import resolve_default_chat_workspace_dir
from app.services.chat.chat_service import ChatService

router = APIRouter()

_DELIVERABLE_REL_PATH = "deliverable_e2e.md"
_DELIVERABLE_WORKSPACE_REF = f"workspace/{_DELIVERABLE_REL_PATH}"
_DELIVERABLE_FILE_CONTENT = "# Deliverable E2E\n\nFixture content for Chrome MCP smoke.\n"
_DELIVERABLE_ASSISTANT_MARKDOWN = (
    f"Deliverable link E2E fixture — open `{_DELIVERABLE_WORKSPACE_REF}` in the portal."
)


@router.post("/test/seed-deliverable-link-fixture", include_in_schema=False)
async def seed_deliverable_link_fixture() -> dict[str, str]:
    """Local dev/test only: seed workspace file + assistant deliverable inline code."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for deliverable link E2E seed",
        )

    agent = agents[0]
    chat_id = f"e2edeliv{uuid4().hex[:8]}"

    workspace_dir = await resolve_default_chat_workspace_dir(chat_id, persist_workspace=True)
    if not workspace_dir:
        raise HTTPException(
            status_code=500,
            detail="Failed to resolve workspace for deliverable link E2E seed",
        )

    file_path = Path(workspace_dir) / _DELIVERABLE_REL_PATH
    file_path.write_text(_DELIVERABLE_FILE_CONTENT, encoding="utf-8")

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Deliverable link Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        "Deliverable link E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        _DELIVERABLE_ASSISTANT_MARKDOWN,
        now,
        timezone,
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent.id,
        "workspace_dir": workspace_dir,
        "deliverable_path": _DELIVERABLE_WORKSPACE_REF,
        "ui_path": f"/{chat_id}",
    }
