"""Local-only clarify refresh Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)

[OUTPUT]
seed_clarify_refresh_fixture: HITL clarify hydrate states (pending|answered|regenerate_sibling|structured_form)

[POS]
Mounted via test_fixtures/__init__.py router include.
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

_CLARIFY_REFRESH_VARIANTS = frozenset(
    {"pending", "answered", "regenerate_sibling", "structured_form"}
)

_STRUCTURED_CLARIFY_FORM: dict[str, object] = {
    "title": "E2E Structured Clarify",
    "questions": [
        {
            "id": "destination",
            "prompt": "Which destination should we plan for?",
            "options": [
                {"id": "paris", "label": "Paris"},
                {"id": "tokyo", "label": "Tokyo"},
            ],
        }
    ],
}


def _build_clarification_extra_data(
    *,
    answered: bool,
    variant: str,
) -> dict[str, object]:
    if variant == "structured_form":
        return {
            "clarification": {
                "answered": answered,
                "title": "E2E Structured Clarify",
                "isResumeMode": True,
                "form": _STRUCTURED_CLARIFY_FORM,
            }
        }
    return {
        "clarification": {
            "answered": answered,
            "title": "E2E Clarify Destination",
            "options": ["Paris", "Tokyo"],
            "allowMultiple": False,
            "isResumeMode": True,
        }
    }


@router.post("/test/seed-clarify-refresh-fixture", include_in_schema=False)
async def seed_clarify_refresh_fixture(variant: str = "pending") -> dict[str, str | bool]:
    """Local dev/test only: seed clarify hydrate states for Chrome READ E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in _CLARIFY_REFRESH_VARIANTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported clarify refresh fixture variant: {variant}",
        )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500, detail="No agents available for clarify refresh E2E seed"
        )

    agent = agents[0]
    agent_id = agent.id
    chat_id = f"e2eclarify{uuid4().hex[:8]}"
    clarify_message_id = str(uuid4())
    answered = normalized == "answered"
    use_structured = normalized == "structured_form"

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Clarify refresh Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        "Clarify refresh E2E fixture question",
        now,
        timezone,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        "Which destination should we plan for?",
        now,
        timezone,
        message_id=clarify_message_id,
        extra_data=_build_clarification_extra_data(
            answered=answered,
            variant="structured_form" if use_structured else normalized,
        ),
    )
    if normalized == "regenerate_sibling":
        await ChatService.append_message(
            chat_id,
            "assistant",
            "Regenerated draft without a new clarify turn.",
            now,
            timezone,
        )

    return {
        "chat_id": chat_id,
        "agent_id": agent_id,
        "clarify_message_id": clarify_message_id,
        "variant": normalized,
        "clarification_answered": answered,
        "ui_path": f"/{chat_id}",
    }
