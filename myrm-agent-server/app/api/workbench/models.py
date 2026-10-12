"""[INPUT]
- None (Pydantic models and pure typing)

[OUTPUT]
- WorkbenchFileNode: Recursive file tree model for workspace explorer
- FileTreeResponse: Root-level file tree container
- FileContentResponse: Raw text content and language metadata
- DiffHunk & FileDiffResponse: Structured unified diff model
- TerminalExecRequest & TerminalExecResponse: Sandbox/host execution payload
- PluginItemModel & PluginProbeResponse: Plugin lifecycle and health check model

[POS]
Data contracts for Independent Multi-Tab Auxiliary Workbench (Item 25).
Strict typing: Zero Any. File length < 180 lines.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal["file", "directory"]
PluginStatus = Literal["healthy", "degraded", "error", "inactive"]


class WorkbenchFileNode(BaseModel):
    name: str = Field(..., description="File or directory name")
    path: str = Field(..., description="Relative or sanitized workspace path")
    node_type: NodeType = Field(..., description="file or directory")
    size_bytes: int = Field(default=0, description="Size in bytes")
    modified_at: str = Field(default="", description="ISO 8601 modified timestamp")
    extension: str = Field(default="", description="File extension without dot")
    children: list[WorkbenchFileNode] | None = Field(
        default=None, description="Children nodes if directory"
    )


class FileTreeResponse(BaseModel):
    root_path: str = Field(..., description="Root directory path")
    nodes: list[WorkbenchFileNode] = Field(default_factory=list)
    total_files: int = Field(default=0)
    total_dirs: int = Field(default=0)


class FileContentResponse(BaseModel):
    path: str = Field(..., description="Relative workspace path")
    content: str = Field(..., description="Decoded text content")
    language: str = Field(default="plaintext", description="Inferred language identifier")
    size_bytes: int = Field(default=0)
    is_binary: bool = Field(default=False)
    modified_at: str = Field(default="")


class DiffHunk(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str] = Field(default_factory=list)


class FileDiffRequest(BaseModel):
    file_path: str = Field(..., description="Path to file being diffed")
    original_content: str | None = Field(default=None, description="Base text content")
    modified_content: str | None = Field(default=None, description="New text content")


class FileDiffResponse(BaseModel):
    file_path: str
    unified_diff: str = Field(default="")
    additions: int = Field(default=0)
    deletions: int = Field(default=0)
    hunks: list[DiffHunk] = Field(default_factory=list)


class TerminalExecRequest(BaseModel):
    command: str = Field(..., min_length=1, description="Shell command string")
    cwd: str | None = Field(default=None, description="Working directory")
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class TerminalExecResponse(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class PluginItemModel(BaseModel):
    plugin_id: str
    name: str
    description: str
    version: str
    author: str
    github_repo: str | None = None
    status: PluginStatus = "healthy"
    is_installed: bool = True
    last_probed_at: str | None = None


class PluginProbeResponse(BaseModel):
    plugin_id: str
    status: PluginStatus
    latency_ms: int
    message: str
    details: dict[str, str] = Field(default_factory=dict)
