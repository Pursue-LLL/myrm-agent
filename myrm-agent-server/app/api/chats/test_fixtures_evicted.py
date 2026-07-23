"""Local-only UECD evicted LiveTerminal Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)
app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: workspace path)
myrm_agent_harness.agent.context_management.infra.evicted_content::build_evicted_basename (POS: spill filename)

[OUTPUT]
seed_evicted_live_terminal_fixture: UECD web_fetch spill + LiveTerminal progressSteps

[POS]
Split from test_fixtures.py for line-budget compliance; mounted via test_fixtures router include.
"""

from __future__ import annotations

import os
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
