"""Local-only file mutation Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)

[OUTPUT]
seed_file_mutation_fixture: empty file_write rejection banner E2E (variant=empty_write)

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

_EMPTY_WRITE_FIXTURE_ANSWER = "Empty write E2E fixture answer."
_EMPTY_WRITE_FIXTURE_PATH = "empty_write_e2e.txt"
_EMPTY_WRITE_ERROR = "Cannot write empty file content"


@router.post("/test/seed-file-mutation-fixture", include_in_schema=False)
async def seed_file_mutation_fixture(
    variant: str = "empty_write",
) -> dict[str, str]:
    """Local dev/test only: seed chat with persisted fileMutationFailures for Chrome E2E.

    variant:
      - empty_write (default): assistant message includes file_write_tool empty-content failure
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in {"empty_write"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file-mutation fixture variant: {variant}",
        )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for file-mutation E2E seed",
        )

    agent = agents[0]
    chat_id = f"e2efmut{uuid4().hex[:8]}"
    message_id = str(uuid4())

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="File mutation Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        "Empty write E2E fixture question",
        now,
        timezone,
    )

    extra_data: dict[str, object] = {
        "fileMutationFailures": [
            {
                "path": _EMPTY_WRITE_FIXTURE_PATH,
                "tool": "file_write_tool",
                "error_preview": _EMPTY_WRITE_ERROR,
            }
        ]
    }
    await ChatService.append_message(
        chat_id,
        "assistant",
        _EMPTY_WRITE_FIXTURE_ANSWER,
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
        "file_path": _EMPTY_WRITE_FIXTURE_PATH,
    }
