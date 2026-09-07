"""Host asset data models and SSH/SFTP execution schemas.

[INPUT]
- pydantic.BaseModel, pydantic.Field
- typing.Literal, typing.Optional, typing.Dict, typing.List

[OUTPUT]
- HostAuthType, HostAssetConfig, SSHCommandRequest, SSHCommandResult
- SFTPReadRequest, SFTPWriteRequest, SFTPTransferResult, HostConfigImportResult

[POS]
Domain data structures for remote host asset management and safe SSH/SFTP bridge.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HostAuthType(str, Enum):
    """Authentication type for remote SSH host connection."""

    PASSWORD = "password"
    PRIVATE_KEY = "private_key"
    AGENT_FORWARD = "agent_forward"


class HostAssetConfig(BaseModel):
    """Configuration model for a managed remote host asset."""

    host_id: str = Field(..., description="Unique identifier for the host asset")
    name: str = Field(..., description="Human-readable alias or display name")
    hostname: str = Field(..., description="Target server IP or domain")
    port: int = Field(default=22, description="SSH port number", ge=1, le=65535)
    username: str = Field(default="root", description="SSH login username")
    auth_type: HostAuthType = Field(
        default=HostAuthType.PRIVATE_KEY, description="Authentication method"
    )
    private_key_path: Optional[str] = Field(
        default=None, description="Local path to private key file if applicable"
    )
    private_key_content: Optional[str] = Field(
        default=None, description="Encrypted or raw private key content string"
    )
    password: Optional[str] = Field(
        default=None, description="SSH login password (if using password auth)"
    )
    passphrase: Optional[str] = Field(
        default=None, description="Passphrase for encrypted private key"
    )
    description: str = Field(default="", description="Optional note or environment info")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")


class SSHCommandRequest(BaseModel):
    """Request payload for executing an SSH command on a managed host."""

    host_id: str = Field(..., description="Target host ID")
    command: str = Field(..., description="Bash command to execute remotely")
    timeout_seconds: float = Field(
        default=30.0, description="Execution timeout in seconds", gt=0
    )
    working_dir: Optional[str] = Field(
        default=None, description="Initial remote working directory"
    )
    env: Dict[str, str] = Field(
        default_factory=dict, description="Environment variables to inject"
    )


class SSHCommandResult(BaseModel):
    """Result of remote SSH command execution."""

    host_id: str = Field(..., description="Target host ID")
    command: str = Field(..., description="Executed command")
    exit_code: int = Field(..., description="Process exit returncode")
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")
    success: bool = Field(..., description="Whether command succeeded (exit_code == 0)")


class SFTPReadRequest(BaseModel):
    """Request payload for reading a remote file via SFTP."""

    host_id: str = Field(..., description="Target host ID")
    remote_path: str = Field(..., description="Absolute remote file path")
    max_bytes: int = Field(
        default=1024 * 1024, description="Maximum bytes to read into memory", gt=0
    )


class SFTPWriteRequest(BaseModel):
    """Request payload for writing/uploading content to a remote file via SFTP."""

    host_id: str = Field(..., description="Target host ID")
    remote_path: str = Field(..., description="Absolute remote destination file path")
    content: str = Field(..., description="File content to write")
    mode: Literal["write", "append"] = Field(
        default="write", description="Write mode (overwrite or append)"
    )


class SFTPTransferResult(BaseModel):
    """Result of an SFTP file read/write operation."""

    host_id: str = Field(..., description="Target host ID")
    remote_path: str = Field(..., description="Target remote file path")
    success: bool = Field(..., description="Whether operation succeeded")
    content: Optional[str] = Field(default=None, description="Read content if applicable")
    bytes_transferred: int = Field(default=0, description="Total bytes processed")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class HostConfigImportResult(BaseModel):
    """Result summary of importing ~/.ssh/config entries."""

    total_parsed: int = Field(..., description="Total host entries parsed")
    total_imported: int = Field(..., description="Total new or updated hosts saved")
    imported_host_ids: List[str] = Field(
        default_factory=list, description="IDs of successfully imported hosts"
    )
    errors: List[str] = Field(default_factory=list, description="Parsing or validation errors")
