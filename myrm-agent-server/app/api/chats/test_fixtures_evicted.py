"""Local-only UECD evicted LiveTerminal Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)
app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: workspace path)
myrm_agent_harness.api.hooks::build_evicted_basename (POS: spill filename)

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
_E2E_BASH_FAIL_STDOUT_LINES = 150
_E2E_BASH_FAIL_STDERR_LINES = 120
_E2E_BASH_FAIL_STDOUT_MARKER = 25
_E2E_BASH_FAIL_STDERR_MARKER = 40


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
      - bash_failure: two evicted streams (stdout + stderr) on one failed bash step
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in {"full", "expired", "bash_failure"}:
        raise HTTPException(
            status_code=400, detail=f"Unsupported evicted fixture variant: {variant}"
        )

    from myrm_agent_harness.api.hooks import build_evicted_basename

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for evicted live terminal E2E seed",
        )

    agent = agents[0]
    chat_id = f"e2euecd{uuid4().hex[:8]}"
    message_id = str(uuid4())

    stdout_filename: str | None = None
    stderr_filename: str | None = None
    if normalized == "bash_failure":
        stdout_filename = build_evicted_basename("output")
        stderr_filename = build_evicted_basename("output")
        stdout_content = "".join(
            f"MYRM_E2E_FAIL_STDOUT_LINE_{index}\n"
            for index in range(_E2E_BASH_FAIL_STDOUT_LINES)
        )
        stderr_content = "".join(
            f"MYRM_E2E_FAIL_STDERR_LINE_{index}\n"
            for index in range(_E2E_BASH_FAIL_STDERR_LINES)
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
            (evicted_dir / stdout_filename).write_text(
                stdout_content, encoding="utf-8"
            )
            (evicted_dir / stderr_filename).write_text(
                stderr_content, encoding="utf-8"
            )
    else:
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
    if normalized == "bash_failure":
        assert stdout_filename is not None and stderr_filename is not None
        stdout_preview = (
            "[LARGE OUTPUT TRUNCATED (150 lines, ~500 tokens)]\n\n"
            + "".join(
                f"MYRM_E2E_FAIL_STDOUT_LINE_{index}\n"
                for index in range(min(40, _E2E_BASH_FAIL_STDOUT_LINES))
            )
            + "\n\n[Truncated: showing head/tail preview only]"
        )
        extra_data: dict[str, object] = {
            "progressSteps": [
                {
                    "step_key": "bash_code_execute_tool",
                    "tool_name": "bash_code_execute_tool",
                    "status": "error",
                    "stdout": stdout_preview,
                    "evicted_file_ref": stdout_filename,
                    "evicted_stored_chars": 150 * len("MYRM_E2E_FAIL_STDOUT_LINE_99\n"),
                    "evicted_total_lines": _E2E_BASH_FAIL_STDOUT_LINES,
                    "evicted_stderr_file_ref": stderr_filename,
                    "evicted_stderr_stored_chars": (
                        120 * len("MYRM_E2E_FAIL_STDERR_LINE_99\n")
                    ),
                    "evicted_stderr_total_lines": _E2E_BASH_FAIL_STDERR_LINES,
                }
            ]
        }
        marker_stdout = (
            f"MYRM_E2E_FAIL_STDOUT_LINE_{_E2E_BASH_FAIL_STDOUT_MARKER}"
        )
        marker_stderr = (
            f"MYRM_E2E_FAIL_STDERR_LINE_{_E2E_BASH_FAIL_STDERR_MARKER}"
        )
    else:
        preview_stdout = (
            "[LARGE OUTPUT TRUNCATED (120 lines, ~500 tokens)]\n\n"
            + content[:800]
            + "\n\n[Truncated: showing head/tail preview only]"
        )
        extra_data = {
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
        marker_stdout = f"MYRM_E2E_UECD_SPILL_LINE_{_UECD_E2E_MARKER_LINE}"
        marker_stderr = ""

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
        "filename": stdout_filename or (filename if normalized != "bash_failure" else ""),
        "ui_path": f"/{chat_id}",
        "marker_line": marker_stdout,
        "marker_stderr_line": marker_stderr,
        "stderr_filename": stderr_filename or "",
        "line_count": _UECD_E2E_LINE_COUNT,
        "agent_id": agent.id,
        "workspace_dir": workspace_dir,
        "variant": normalized,
    }
