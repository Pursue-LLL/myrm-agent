"""Data models for Multi-Host SSH Operations, SFTP Explorer, and Agent Asset Bridge.

[INPUT]
- pydantic::BaseModel, Field
- typing::Any, Dict, List, Optional, Literal
- enum::Enum

[OUTPUT]
- HostAuthMethod, SSHHostAsset, SSHExecResult, SFTPItemInfo, HostConnectionStatus

[POS]
Domain models in app/services/ssh_bridge/models.py.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HostAuthMethod(str, enum.Enum):
    """Authentication method for remote SSH hosts."""

    KEY_FILE = "key_file"
    PASSWORD = "password"
    AGENT = "agent"


class SSHHostAsset(BaseModel):
    """Strongly typed host asset descriptor."""

    host_id: str = Field(..., description="Unique host asset identifier (e.g. host_gpu_node_1)")
    alias: str = Field(..., description="Human-friendly alias/name for the server")
    hostname: str = Field(..., description="Target hostname or IP address")
    port: int = Field(default=22, ge=1, le=65535, description="SSH connection port")
    username: str = Field(..., description="Login username")
    auth_method: HostAuthMethod = Field(default=HostAuthMethod.KEY_FILE, description="Authentication mechanism")
    key_path: Optional[str] = Field(default=None, description="Path to identity file (if key_file auth)")
    encrypted_secret: Optional[str] = Field(default=None, description="Encrypted password or passphrase (AES-GCM)")
    tags: List[str] = Field(default_factory=list, description="Categorization tags (e.g. ['prod', 'gpu'])")
    description: Optional[str] = Field(default=None, description="Optional server description")
    created_at: float = Field(default=0.0, description="Timestamp of asset registration")
    is_trusted: bool = Field(default=False, description="Whether Agent is pre-authorized for safe non-destructive ops")


class SSHExecResult(BaseModel):
    """Result of remote command execution."""

    host_id: str = Field(..., description="Target host ID")
    command: str = Field(..., description="Executed command")
    exit_code: int = Field(..., description="Process exit code (0 for success)")
    stdout: str = Field(default="", description="Cleaned standard output stream")
    stderr: str = Field(default="", description="Cleaned standard error stream")
    distilled_summary: Optional[str] = Field(default=None, description="High-entropy distilled summary of output")
    duration_ms: int = Field(default=0, description="Execution duration in milliseconds")
    is_truncated: bool = Field(default=False, description="Whether output exceeded buffer limit and was truncated")


class SFTPItemInfo(BaseModel):
    """File or directory metadata in SFTP remote filesystem."""

    filename: str = Field(..., description="Name of the file or directory")
    path: str = Field(..., description="Absolute remote path")
    is_dir: bool = Field(default=False, description="Whether item is a directory")
    size_bytes: int = Field(default=0, ge=0, description="File size in bytes")
    mtime: int = Field(default=0, description="Last modification timestamp")
    permissions: Optional[str] = Field(default=None, description="Octal or POSIX permissions string (e.g. '0755')")


class HostConnectionStatus(BaseModel):
    """Active connection and health telemetry for a host."""

    host_id: str = Field(..., description="Target host ID")
    is_online: bool = Field(default=False, description="Whether host is reachable via SSH handshake")
    latency_ms: Optional[float] = Field(default=None, description="Round-trip handshake latency in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Detailed diagnostic error if unreachable")
    last_checked_at: float = Field(default=0.0, description="Timestamp of last health check probe")
