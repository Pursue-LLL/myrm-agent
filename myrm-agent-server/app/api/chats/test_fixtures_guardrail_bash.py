"""Local-only guardrail bash Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.agent.agent_service::AgentService (POS: resolve default agent)
- app.services.chat.chat_service::ChatService (POS: seed chat + messages)

[OUTPUT]
- router: POST /test/seed-guardrail-bash-fixture (POS: E2E seed endpoint)

[POSITION] app.api.chats — Chrome E2E test fixture for bash myrm_tools guardrail Badge UI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_FIXTURE_ANSWER = "Guardrail bash Chrome E2E fixture answer."

_VARIANTS: dict[str, dict[str, str]] = {
    "direct_import": {
        "user": "Run bash with import myrm_tools (fixture).",
        "command": "import myrm_tools",
        "error": "Command blocked: `import myrm_tools` is not available in bash_code_execute_tool.",
    },
    "pipe_stdin": {
        "user": "Run printf pipe to python3 with myrm_tools (fixture).",
        "command": 'printf "import myrm_tools" | python3',
        "error": "Command blocked: `import myrm_tools` is not available in bash_code_execute_tool.",
    },
    "python_m": {
        "user": "Run python3 -m myrm_tools (fixture).",
        "command": "python3 -m myrm_tools",
        "error": "Command blocked: `import myrm_tools` is not available in bash_code_execute_tool.",
    },
}


@router.post("/test/seed-guardrail-bash-fixture", include_in_schema=False)
async def seed_guardrail_bash_fixture(
    variant: str = Query("direct_import", description="Fixture variant key"),
) -> dict[str, str]:
    """Local dev/test only: seed chat with guardrail_blocked bash progress step."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    spec = _VARIANTS.get(variant.strip())
    if spec is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown variant {variant!r}; expected one of {sorted(_VARIANTS)}",
        )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for guardrail bash E2E seed",
        )

    agent = agents[0]
    chat_id = f"e2eguard{uuid4().hex[:8]}"
    message_id = str(uuid4())

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title=f"Guardrail bash E2E ({variant})",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        spec["user"],
        now,
        timezone,
    )

    extra_data: dict[str, object] = {
        "progressSteps": [
            {
                "step_key": "bash_code_execute_tool",
                "tool_name": "bash_code_execute_tool",
                "status": "error",
                "error": True,
                "error_category": "guardrail_blocked",
                "reason": spec["error"],
                "items": [{"code": spec["command"]}],
            },
        ]
    }
    await ChatService.append_message(
        chat_id,
        "assistant",
        _FIXTURE_ANSWER,
        now,
        timezone,
        message_id=message_id,
        extra_data=extra_data,
    )

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "variant": variant,
        "ui_path": f"/{chat_id}",
        "agent_id": agent.id,
    }
