"""Local-only seed for context retention Chrome READ E2E (summary + pins + bookmarks).

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.agent.agent_service::AgentService (POS: resolve default agent)
- app.services.chat.chat_service::ChatService (POS: seed chat + messages + compaction)
- myrm_agent_harness.runtime.context.context_branches::append_context_branch (POS: snapshot bookmark)
- myrm_agent_harness.runtime.context.session_context_pins::write_pinned_files (POS: file pins)

[OUTPUT]
- router: POST /test/seed-context-retention-fixture (POS: E2E seed endpoint)

[POSITION] app.api.chats — Chrome E2E test fixture for context retention UI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.runtime.context.context_branches import append_context_branch
from myrm_agent_harness.runtime.context.session_context_pins import write_pinned_files

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_SUMMARY_TEXT = (
    "E2E context retention summary fixture — user asked about auth module refactor."
)
_PIN_FILE = "src/context/retention.py"
_BRANCH_LABEL = "Before compaction E2E"
_SNAPSHOT_PATH = ".context/snap-e2e-retention.jsonl"


def _build_assistant_extra_data() -> dict[str, object]:
    return {
        "usage": {
            "prompt_tokens": 52_000,
            "completion_tokens": 800,
            "total_tokens": 52_800,
        },
        "contextBudget": {
            "current_tokens": 52_000,
            "max_context_tokens": 128_000,
            "usage_percent": 40.6,
            "health_status": "healthy",
        },
    }


@router.post("/test/seed-context-retention-fixture", include_in_schema=False)
async def seed_context_retention_fixture() -> dict[str, str | list[str]]:
    """Local dev/test only: seed compacted summary, pins, and snapshot bookmarks for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500, detail="No agents available for context retention E2E seed"
        )

    agent = agents[0]
    agent_id = agent.id

    chat_id = f"e2econtextret{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Context retention Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"

    await ChatService.append_message(
        chat_id,
        "user",
        "Context retention E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        "Context retention E2E fixture answer with context budget metadata.",
        now,
        timezone,
        extra_data=_build_assistant_extra_data(),
    )

    await ChatService.update_chat_fields(
        chat_id,
        {
            "compacted_summary": _SUMMARY_TEXT,
            "compacted_at": now,
            "compacted_tokens_saved": 1_500,
        },
    )

    write_pinned_files(chat_id, [_PIN_FILE])
    append_context_branch(
        chat_id,
        snapshot_path=_SNAPSHOT_PATH,
        label=_BRANCH_LABEL,
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent_id,
        "summary_text": _SUMMARY_TEXT,
        "pinned_files": [_PIN_FILE],
        "bookmark_label": _BRANCH_LABEL,
        "snapshot_path": _SNAPSHOT_PATH,
        "ui_path": f"/{chat_id}",
    }
