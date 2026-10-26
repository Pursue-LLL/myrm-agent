"""[INPUT]
- TerminalExecRequest, TerminalExecResponse from .models
- app.services.chat.effective_workspace::find_chat_workspace_root (POS: the workspace a chat's runs work in)
- myrm_agent_harness.api::build_isolated_child_env, EnvInheritPolicy (POS: credential-free child process environment)
- myrm_agent_harness.agent.hooks.command_gate::gate_hook_command (POS: dangerous-command gate for person-authored shell commands)
- myrm_agent_harness.utils.os_compat::get_process_group_kwargs, kill_process_group (POS: cross-platform process-tree control)

[OUTPUT]
- workbench_router: FastAPI APIRouter exposing a chat workspace's command terminal

[POS]
Backend endpoint for the auxiliary workbench terminal. The working directory is confined to the workspace of the
chat the request names; commands run there under a static safety gate, with the same credential-free environment
as the agent's own shell, a process tree killed when the wait times out or its task is cancelled, and a per-stream
output cap. File browsing and previews are served by the shared ``/files/browse`` API, not here.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.hooks.command_gate import gate_hook_command
from myrm_agent_harness.api import EnvInheritPolicy, build_isolated_child_env
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs, kill_process_group

from app.services.chat.effective_workspace import find_chat_workspace_root

from .models import TerminalExecRequest, TerminalExecResponse

workbench_router = APIRouter()

_MAX_RESPONSE_BYTES = 1_000_000
_READ_CHUNK_BYTES = 65_536


async def _workspace_root(chat_id: str) -> Path:
    """The existing workspace directory of ``chat_id``; there is no stand-in for a chat that has none."""
    found = await find_chat_workspace_root(chat_id)
    root = found.resolve() if found is not None else None
    if root is None or not root.is_dir():
        raise HTTPException(status_code=404, detail="Workspace directory not found")
    return root


def _resolve_safe_path(target_path_str: str, root: Path) -> Path:
    target = Path(target_path_str) if os.path.isabs(target_path_str) else root / target_path_str
    target = target.resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=403, detail="Path traversal forbidden: outside workspace boundary")
    return target


async def _read_capped(stream: asyncio.StreamReader) -> tuple[bytes, bool]:
    """Read ``stream`` to EOF, keeping at most ``_MAX_RESPONSE_BYTES``; the rest is drained and dropped."""
    kept = bytearray()
    truncated = False
    while chunk := await stream.read(_READ_CHUNK_BYTES):
        room = _MAX_RESPONSE_BYTES - len(kept)
        kept += chunk[:room]
        truncated = truncated or len(chunk) > room
    return bytes(kept), truncated


@workbench_router.post("/terminal/exec", response_model=TerminalExecResponse)
async def execute_terminal_command(req: TerminalExecRequest) -> TerminalExecResponse:
    if (refusal := gate_hook_command(req.command, strict=False)) is not None:
        raise HTTPException(status_code=400, detail=f"Command rejected by safety guard: {refusal}")

    root = await _workspace_root(req.chat_id)
    cwd = _resolve_safe_path(req.cwd, root) if req.cwd else root
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail=f"Working directory not found: {req.cwd}")

    start_time = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_shell(
            req.command,
            cwd=str(cwd),
            env=build_isolated_child_env(inherit_policy=EnvInheritPolicy.CORE),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **get_process_group_kwargs(),
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Execution error: {exc}") from exc

    assert proc.stdout is not None and proc.stderr is not None
    try:
        (stdout, stdout_cut), (stderr, stderr_cut), _ = await asyncio.wait_for(
            asyncio.gather(_read_capped(proc.stdout), _read_capped(proc.stderr), proc.wait()),
            timeout=float(req.timeout_seconds),
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=f"Command execution timed out after {req.timeout_seconds}s") from exc
    finally:
        # Timeout or a cancelled handler task ends the wait here and no command outlives it; a client disconnect cancels nothing.
        if proc.returncode is None:
            kill_process_group(proc.pid)
            await proc.wait()

    return TerminalExecResponse(
        command=req.command,
        exit_code=proc.returncode if proc.returncode is not None else 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        duration_ms=int((time.perf_counter() - start_time) * 1000),
        truncated=stdout_cut or stderr_cut,
    )
