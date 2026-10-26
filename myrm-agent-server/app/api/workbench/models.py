"""[INPUT]
- None (Pydantic models and pure typing)

[OUTPUT]
- WorkbenchFileNode: Recursive file tree model for workspace explorer
- FileTreeResponse: Root-level file tree container
- FileContentResponse: Raw text content and language metadata
- TerminalExecRequest & TerminalExecResponse: Command execution payload

[POS]
Data contracts for the auxiliary workbench: a chat workspace's file explorer and command terminal.
Strict typing: Zero Any.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal["file", "directory"]


class WorkbenchFileNode(BaseModel):
    name: str = Field(..., description="File or directory name")
    path: str = Field(..., description="Path relative to the chat workspace")
    node_type: NodeType = Field(..., description="file or directory")
    size_bytes: int = Field(default=0, description="Size in bytes")
    modified_at: str = Field(default="", description="ISO 8601 modified timestamp")
    extension: str = Field(default="", description="File extension without dot")
    children: list[WorkbenchFileNode] | None = Field(default=None, description="Children nodes if directory")


class FileTreeResponse(BaseModel):
    root_path: str = Field(..., description="Root directory path")
    nodes: list[WorkbenchFileNode] = Field(default_factory=list)
    total_files: int = Field(default=0)
    total_dirs: int = Field(default=0)


class FileContentResponse(BaseModel):
    path: str = Field(..., description="Path relative to the chat workspace")
    content: str = Field(..., description="Decoded text content")
    language: str = Field(default="plaintext", description="Inferred language identifier")
    size_bytes: int = Field(default=0)
    is_binary: bool = Field(default=False)
    modified_at: str = Field(default="")


class TerminalExecRequest(BaseModel):
    chat_id: str = Field(..., min_length=1, description="Chat whose workspace the command runs in")
    command: str = Field(..., min_length=1, description="Shell command string")
    cwd: str | None = Field(default=None, description="Working directory inside the chat workspace")
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class TerminalExecResponse(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = Field(default=False, description="Output exceeded the per-stream cap and was cut")
