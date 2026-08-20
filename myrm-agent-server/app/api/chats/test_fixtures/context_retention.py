"""Local-only seed for context retention Chrome READ E2E (summary + pins + bookmarks).

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.agent.agent_service::AgentService (POS: resolve default agent)
- app.services.chat.chat_service::ChatService (POS: seed chat + messages + compaction)
- myrm_agent_harness.runtime.context.context_branches::append_context_branch (POS: snapshot bookmark)
- myrm_agent_harness.runtime.context.session.session_context_pins::write_pinned_files (POS: file pins)

[OUTPUT]
- router: POST /test/seed-context-retention-fixture (POS: E2E seed endpoint)

[POS]
Sub-package of app.api.chats.test_fixtures. Chrome E2E test fixture for context retention UI (local-only).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import myrm_agent_harness.runtime.execution_paths as execution_paths
from fastapi import APIRouter, HTTPException
from myrm_agent_harness.runtime.context.context_branches import append_context_branch
from myrm_agent_harness.runtime.context.session.session_context_pins import (
    write_pinned_files,
)

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_SUMMARY_TEXT = "E2E context retention summary fixture — user asked about auth module refactor."
_PIN_FILE = "src/context/retention.py"
_BRANCH_LABEL = "Before compaction E2E"


def _write_seed_snapshot(chat_id: str) -> str:
    rel_path = f".context/{chat_id}/snapshots/e2e-pre-compact.jsonl"
    abs_path = Path(execution_paths.PERSISTENT_ROOT) / ".context" / chat_id / "snapshots" / "e2e-pre-compact.jsonl"
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"_meta": True, "message_count": 2, "chat_id": chat_id}, ensure_ascii=False),
        json.dumps(
            {"type": "human", "content": "Context retention E2E fixture question"},
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "type": "ai",
                "content": "Context retention E2E fixture answer with context budget metadata.",
            },
            ensure_ascii=False,
        ),
    ]
    abs_path.write_text("\n".join(lines), encoding="utf-8")
    return rel_path


def _build_assistant_extra_data() -> dict[str, object]:
    return {
        "usage": {
            "prompt_tokens": 52_000,
            "completion_tokens": 800,
            "total_tokens": 52_800,
        },
        "contextBudget": {
            "current_tokens": 118_000,
            "max_context_tokens": 128_000,
            "usage_percent": 92.2,
            "health_status": "critical",
            "messages_estimated_tokens": 112_000,
            "bound_tools_overhead_tokens": 6_000,
            "other_tokens": 0,
        },
    }


@router.post("/test/seed-context-retention-fixture", include_in_schema=False)
async def seed_context_retention_fixture() -> dict[str, str | list[str]]:
    """Local dev/test only: seed compacted summary, pins, and snapshot bookmarks for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for context retention E2E seed")

    agent = agents[0]
    agent_id = agent.id

    chat_id = f"e2econtextret{uuid4().hex[:8]}"
    seed_workspace = str(Path(execution_paths.PERSISTENT_ROOT) / "e2e-context-retention")
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Context retention Chrome E2E",
            agent_id=agent_id,
            messages=[],
            workspace_dir=seed_workspace,
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
    snapshot_path = _write_seed_snapshot(chat_id)
    append_context_branch(
        chat_id,
        snapshot_path=snapshot_path,
        label=_BRANCH_LABEL,
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent_id,
        "summary_text": _SUMMARY_TEXT,
        "pinned_files": [_PIN_FILE],
        "bookmark_label": _BRANCH_LABEL,
        "snapshot_path": snapshot_path,
        "ui_path": f"/{chat_id}",
    }
