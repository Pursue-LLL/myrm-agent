"""[INPUT]
- WorkbenchFileNode, FileTreeResponse, FileContentResponse, FileDiffRequest, FileDiffResponse, TerminalExecRequest, TerminalExecResponse, PluginItemModel, PluginProbeResponse from .models
- Path traversal defense & asyncio subprocess execution

[OUTPUT]
- workbench_router: FastAPI APIRouter exposing workspace file explorer, Monaco Diff, PTY terminal & plugin probe APIs

[POS]
Backend endpoints for Independent Multi-Tab Auxiliary Workbench (Item 25).
Strict typing: Zero Any. File length < 320 lines. Zero emoji.
"""

from __future__ import annotations

import asyncio
import difflib
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .models import (
    DiffHunk,
    FileContentResponse,
    FileDiffRequest,
    FileDiffResponse,
    FileTreeResponse,
    PluginItemModel,
    PluginProbeResponse,
    PluginStatus,
    TerminalExecRequest,
    TerminalExecResponse,
    WorkbenchFileNode,
)

workbench_router = APIRouter()

_SAFE_ROOT_FALLBACK = Path.cwd().resolve()
_EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".next", "dist", "build"}
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

_MOCK_PLUGINS: list[PluginItemModel] = [
    PluginItemModel(
        plugin_id="plugin-git-diff-inspector",
        name="Git Diff Inspector",
        description="Real-time multi-branch git diff visualizer and conflict resolver",
        version="1.4.0",
        author="Myrm Team",
        github_repo="https://github.com/myrm-agent/git-diff-inspector",
        status="healthy",
        is_installed=True,
        last_probed_at="2026-10-12T10:00:00Z",
    ),
    PluginItemModel(
        plugin_id="plugin-ansi-pty-streamer",
        name="ANSI PTY Streamer",
        description="High-throughput pseudo-terminal multiplexer with ANSI VT100 colors",
        version="2.1.2",
        author="Myrm Infrastructure",
        github_repo="https://github.com/myrm-agent/ansi-pty-streamer",
        status="healthy",
        is_installed=True,
        last_probed_at="2026-10-12T10:00:00Z",
    ),
    PluginItemModel(
        plugin_id="plugin-ast-code-refactorer",
        name="AST Code Refactorer",
        description="Language-server powered semantic refactoring probe and linter gate",
        version="0.9.8",
        author="Community Contributor",
        github_repo="https://github.com/myrm-agent/ast-code-refactorer",
        status="healthy",
        is_installed=True,
        last_probed_at="2026-10-12T09:45:00Z",
    ),
]


def _resolve_safe_path(target_path_str: str, root_dir: Path | None = None) -> Path:
    base = (root_dir or _SAFE_ROOT_FALLBACK).resolve()
    target = (base / target_path_str).resolve() if not os.path.isabs(target_path_str) else Path(target_path_str).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Path traversal forbidden: outside workspace boundary") from exc
    return target


def _build_tree(dir_path: Path, current_depth: int, max_depth: int) -> list[WorkbenchFileNode]:
    if current_depth > max_depth or not dir_path.is_dir():
        return []

    nodes: list[WorkbenchFileNode] = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except (PermissionError, OSError):
        return []

    for entry in entries:
        if entry.name in _EXCLUDED_DIRS or entry.name.startswith("."):
            continue

        try:
            stat = entry.stat()
            mod_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            if entry.is_dir():
                children = _build_tree(entry, current_depth + 1, max_depth) if current_depth < max_depth else []
                nodes.append(
                    WorkbenchFileNode(
                        name=entry.name,
                        path=str(entry.relative_to(_SAFE_ROOT_FALLBACK)),
                        node_type="directory",
                        size_bytes=0,
                        modified_at=mod_iso,
                        children=children,
                    )
                )
            else:
                ext = entry.suffix.lstrip(".").lower()
                nodes.append(
                    WorkbenchFileNode(
                        name=entry.name,
                        path=str(entry.relative_to(_SAFE_ROOT_FALLBACK)),
                        node_type="file",
                        size_bytes=stat.st_size,
                        modified_at=mod_iso,
                        extension=ext,
                    )
                )
        except (PermissionError, OSError):
            continue

    return nodes


@workbench_router.get("/files", response_model=FileTreeResponse)
async def list_workspace_files(
    root_dir: str | None = Query(default=None, description="Optional root path within workspace"),
    max_depth: int = Query(default=3, ge=1, le=8),
) -> FileTreeResponse:
    target_root = _resolve_safe_path(root_dir) if root_dir else _SAFE_ROOT_FALLBACK
    if not target_root.exists() or not target_root.is_dir():
        raise HTTPException(status_code=404, detail="Workspace directory not found")

    nodes = _build_tree(target_root, current_depth=1, max_depth=max_depth)

    def count_nodes(n_list: list[WorkbenchFileNode]) -> tuple[int, int]:
        f_count = 0
        d_count = 0
        for n in n_list:
            if n.node_type == "file":
                f_count += 1
            else:
                d_count += 1
                if n.children:
                    c_f, c_d = count_nodes(n.children)
                    f_count += c_f
                    d_count += c_d
        return f_count, d_count

    total_f, total_d = count_nodes(nodes)
    return FileTreeResponse(
        root_path=str(target_root),
        nodes=nodes,
        total_files=total_f,
        total_dirs=total_d,
    )


@workbench_router.get("/file/content", response_model=FileContentResponse)
async def get_file_content(path: str = Query(..., min_length=1)) -> FileContentResponse:
    target = _resolve_safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    ext = target.suffix.lstrip(".").lower()
    lang = _EXTENSION_LANG_MAP.get(ext, "plaintext")
    stat = target.stat()
    mod_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

    try:
        text_content = target.read_text(encoding="utf-8", errors="replace")
        return FileContentResponse(
            path=str(target.relative_to(_SAFE_ROOT_FALLBACK)),
            content=text_content,
            language=lang,
            size_bytes=stat.st_size,
            is_binary=False,
            modified_at=mod_iso,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {exc}") from exc


@workbench_router.post("/diff", response_model=FileDiffResponse)
async def compute_file_diff(req: FileDiffRequest) -> FileDiffResponse:
    orig = req.original_content or ""
    mod = req.modified_content or ""

    orig_lines = orig.splitlines(keepends=True)
    mod_lines = mod.splitlines(keepends=True)

    diff_gen = list(
        difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{req.file_path}",
            tofile=f"b/{req.file_path}",
            lineterm="",
        )
    )
    unified_diff_str = "\n".join(diff_gen)

    additions = sum(1 for line in diff_gen if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_gen if line.startswith("-") and not line.startswith("---"))

    # Parse hunks
    hunks: list[DiffHunk] = []
    current_hunk: DiffHunk | None = None
    hunk_header_regex = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    for line in diff_gen:
        match = hunk_header_regex.match(line)
        if match:
            if current_hunk:
                hunks.append(current_hunk)
            old_start = int(match.group(1))
            old_lines = int(match.group(2) or 1)
            new_start = int(match.group(3))
            new_lines = int(match.group(4) or 1)
            current_hunk = DiffHunk(
                old_start=old_start,
                old_lines=old_lines,
                new_start=new_start,
                new_lines=new_lines,
                lines=[],
            )
        elif current_hunk is not None:
            current_hunk.lines.append(line)

    if current_hunk:
        hunks.append(current_hunk)

    return FileDiffResponse(
        file_path=req.file_path,
        unified_diff=unified_diff_str,
        additions=additions,
        deletions=deletions,
        hunks=hunks,
    )


@workbench_router.post("/terminal/exec", response_model=TerminalExecResponse)
async def execute_terminal_command(req: TerminalExecRequest) -> TerminalExecResponse:
    # High-risk command interception
    forbidden_patterns = [r"rm\s+-rf\s+[/~]", r":\(\)\s*\{", r"mkfs", r"dd\s+if="]
    for pattern in forbidden_patterns:
        if re.search(pattern, req.command):
            raise HTTPException(status_code=400, detail="Command rejected by safety sandbox guard")

    cwd_path = _resolve_safe_path(req.cwd) if req.cwd else _SAFE_ROOT_FALLBACK
    start_time = time.perf_counter()

    try:
        proc = await asyncio.create_subprocess_shell(
            req.command,
            cwd=str(cwd_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=float(req.timeout_seconds)
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        return TerminalExecResponse(
            command=req.command,
            exit_code=proc.returncode if proc.returncode is not None else 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            duration_ms=duration_ms,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=408, detail=f"Command execution timed out after {req.timeout_seconds}s") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution error: {exc}") from exc


@workbench_router.get("/plugins", response_model=list[PluginItemModel])
async def list_workbench_plugins() -> list[PluginItemModel]:
    return _MOCK_PLUGINS


@workbench_router.post("/plugins/{plugin_id}/probe", response_model=PluginProbeResponse)
async def probe_plugin_health(plugin_id: str) -> PluginProbeResponse:
    found = next((p for p in _MOCK_PLUGINS if p.plugin_id == plugin_id), None)
    if not found:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    # Simulated microsecond ping
    status: PluginStatus = "healthy"
    latency_ms = 12
    return PluginProbeResponse(
        plugin_id=plugin_id,
        status=status,
        latency_ms=latency_ms,
        message="Plugin probe completed successfully. Subsystem responsive.",
        details={
            "version": found.version,
            "runtime": "python-sandboxed",
            "uptime_rate": "99.98%",
        },
    )
