"""[INPUT]
- WorkbenchFileNode, FileTreeResponse, FileContentResponse, TerminalExecRequest, TerminalExecResponse from .models
- app.services.chat.effective_workspace::find_chat_workspace_root (POS: the workspace a chat's runs work in)
- myrm_agent_harness.api::build_isolated_child_env, EnvInheritPolicy (POS: credential-free child process environment)
- myrm_agent_harness.agent.hooks.command_gate::gate_hook_command (POS: dangerous-command gate for person-authored shell commands)
- myrm_agent_harness.utils.os_compat::get_process_group_kwargs, kill_process_group (POS: cross-platform process-tree control)

[OUTPUT]
- workbench_router: FastAPI APIRouter exposing a chat workspace's file explorer and command terminal

[POS]
Backend endpoints for the auxiliary workbench. Every path is confined to the workspace of the chat the
request names; commands run there under a static safety gate, with the same credential-free environment as the
agent's own shell, a process tree killed when the wait times out or its task is cancelled, and a per-stream output cap. File previews are
capped the same way and binary files are reported instead of decoded.
"""

from __future__ import annotations

import asyncio
import codecs
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.agent.hooks.command_gate import gate_hook_command
from myrm_agent_harness.api import EnvInheritPolicy, build_isolated_child_env
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs, kill_process_group

from app.services.chat.effective_workspace import find_chat_workspace_root

from .models import (
    FileContentResponse,
    FileTreeResponse,
    TerminalExecRequest,
    TerminalExecResponse,
    WorkbenchFileNode,
)

workbench_router = APIRouter()

_EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".next", "dist", "build"}
_MAX_RESPONSE_BYTES = 1_000_000
_READ_CHUNK_BYTES = 65_536
_BINARY_SNIFF_BYTES = 8192
_EXTENSION_LANG_MAP: dict[str, str] = {
    "py": "python",
    "ts": "typescript",
    "tsx": "typescript",
    "js": "javascript",
    "jsx": "javascript",
    "json": "json",
    "md": "markdown",
    "html": "html",
    "css": "css",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
    "yml": "yaml",
    "yaml": "yaml",
    "toml": "toml",
    "sql": "sql",
}


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


def _iso_mtime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def _build_tree(dir_path: Path, root: Path, current_depth: int, max_depth: int) -> list[WorkbenchFileNode]:
    if current_depth > max_depth or not dir_path.is_dir():
        return []

    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return []

    nodes: list[WorkbenchFileNode] = []
    for entry in entries:
        if entry.name in _EXCLUDED_DIRS or entry.name.startswith("."):
            continue

        try:
            stat = entry.stat()
            relative = str(entry.relative_to(root))
            if entry.is_dir():
                children = _build_tree(entry, root, current_depth + 1, max_depth) if current_depth < max_depth else []
                nodes.append(
                    WorkbenchFileNode(
                        name=entry.name,
                        path=relative,
                        node_type="directory",
                        modified_at=_iso_mtime(stat.st_mtime),
                        children=children,
                    )
                )
            else:
                nodes.append(
                    WorkbenchFileNode(
                        name=entry.name,
                        path=relative,
                        node_type="file",
                        size_bytes=stat.st_size,
                        modified_at=_iso_mtime(stat.st_mtime),
                        extension=entry.suffix.lstrip(".").lower(),
                    )
                )
        except OSError:
            continue

    return nodes


def _count_nodes(nodes: list[WorkbenchFileNode]) -> tuple[int, int]:
    files = dirs = 0
    for node in nodes:
        if node.node_type == "file":
            files += 1
            continue
        dirs += 1
        child_files, child_dirs = _count_nodes(node.children or [])
        files += child_files
        dirs += child_dirs
    return files, dirs


@workbench_router.get("/files", response_model=FileTreeResponse)
async def list_workspace_files(
    chat_id: str = Query(..., min_length=1, description="Chat whose workspace to browse"),
    root_dir: str | None = Query(default=None, description="Optional sub-directory within the workspace"),
    max_depth: int = Query(default=3, ge=1, le=8),
) -> FileTreeResponse:
    root = await _workspace_root(chat_id)
    target_root = _resolve_safe_path(root_dir, root) if root_dir else root
    if not target_root.is_dir():
        raise HTTPException(status_code=404, detail="Workspace directory not found")

    nodes = await asyncio.to_thread(_build_tree, target_root, root, 1, max_depth)
    total_files, total_dirs = _count_nodes(nodes)
    return FileTreeResponse(nodes=nodes, total_files=total_files, total_dirs=total_dirs)


def _read_preview(path: Path) -> tuple[str, bool, bool]:
    """Read at most ``_MAX_RESPONSE_BYTES`` of ``path`` as text: ``(text, is_binary, truncated)``.

    A NUL byte near the start marks the file binary (no text is returned). A cut that lands inside a multi-byte
    character drops the partial character instead of emitting a replacement mark.
    """
    with path.open("rb") as handle:
        raw = handle.read(_MAX_RESPONSE_BYTES + 1)
    if b"\0" in raw[:_BINARY_SNIFF_BYTES]:
        return "", True, False
    truncated = len(raw) > _MAX_RESPONSE_BYTES
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    return decoder.decode(raw[:_MAX_RESPONSE_BYTES], final=not truncated), False, truncated


@workbench_router.get("/file/content", response_model=FileContentResponse)
async def get_file_content(
    chat_id: str = Query(..., min_length=1, description="Chat whose workspace holds the file"),
    path: str = Query(..., min_length=1),
) -> FileContentResponse:
    root = await _workspace_root(chat_id)
    target = _resolve_safe_path(path, root)
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    try:
        stat = target.stat()
        content, is_binary, truncated = await asyncio.to_thread(_read_preview, target)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {exc}") from exc

    return FileContentResponse(
        path=str(target.relative_to(root)),
        content=content,
        language=_EXTENSION_LANG_MAP.get(target.suffix.lstrip(".").lower(), "plaintext"),
        size_bytes=stat.st_size,
        is_binary=is_binary,
        truncated=truncated,
        modified_at=_iso_mtime(stat.st_mtime),
    )


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
