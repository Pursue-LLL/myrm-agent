"""Models for Multi-Host SSH Ops, SFTP Explorer and Agent Asset Bridge.

[INPUT]
- Standard Python dataclasses, enums, typing

[OUTPUT]
- SSHAuthMethod, SSHHostAsset, SSHConfigParsedHost, SSHCommandResult, SFTPFileMetadata, SFTPTransferResult

[POS]
Data structures in app/services/ssh_bridge/.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


class SSHAuthMethod(str, enum.Enum):
    """Authentication methods supported for SSH connections."""

    KEY_FILE = "key_file"
    PASSWORD = "password"
    AGENT = "agent"
    NONE = "none"


@dataclass(frozen=True)
class SSHConfigParsedHost:
    """Parsed representation of a host section from ~/.ssh/config."""

    pattern: str
    host_name: str | None = None
    user: str | None = None
    port: int = 22
    identity_file: str | None = None
    proxy_jump: str | None = None
    forward_agent: bool = False
    custom_options: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SSHHostAsset:
    """Registered SSH host asset available for UI and AI Agent dispatch."""

    asset_id: str
    alias: str
    host_name: str
    port: int = 22
    user: str = "root"
    auth_method: SSHAuthMethod = SSHAuthMethod.KEY_FILE
    identity_file_path: str | None = None
    has_encrypted_passphrase: bool = False
    proxy_jump: str | None = None
    tags: tuple[str, ...] = ()
    description: str = ""
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class SSHCommandResult:
    """Structured result of executing a remote command via SSH bridge."""

    asset_alias: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    is_truncated: bool = False
    is_blocked: bool = False
    block_reason: str | None = None


@dataclass(frozen=True)
class SFTPFileMetadata:
    """Metadata of a remote file or directory retrieved via SFTP."""

    filename: str
    path: str
    size_bytes: int
    is_directory: bool
    modified_time_iso: str
    permissions: str = "0644"


@dataclass(frozen=True)
class SFTPTransferResult:
    """Structured result of an SFTP upload/download transfer operation."""

    asset_alias: str
    direction: str  # "upload" or "download"
    local_path: str
    remote_path: str
    bytes_transferred: int
    success: bool
    duration_ms: float
    sha256_checksum: str | None = None
    error_message: str | None = None
