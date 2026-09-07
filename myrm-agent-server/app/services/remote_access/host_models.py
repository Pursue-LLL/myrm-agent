"""Data models for remote host asset management, SSH execution, and SFTP file operations.

[INPUT]
- pydantic::BaseModel, Field
- typing::Any, Dict, List, Optional
- pathlib::Path, re

[OUTPUT]
- RemoteHostConfig: Normalized SSH host connection configuration
- SSHCommandExecutionResult: Structured result of remote command execution
- SFTPTransferResult: Structured result of remote file transfer
- parse_ssh_config_text: Pure parser converting ~/.ssh/config format to list of RemoteHostConfig

[POS]
Domain models and parser for app/services/remote_access/.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

_HOST_ALIAS_RE = re.compile(r"^[a-zA-Z0-9_\.\-]+$")


class RemoteHostConfig(BaseModel):
    """Normalized configuration for a remote SSH/SFTP host asset."""

    alias: str = Field(..., description="Unique host alias or label (e.g. 'gpu-worker-1')")
    hostname: str = Field(..., description="IP address or domain name of the remote host")
    port: int = Field(default=22, ge=1, le=65535, description="SSH port number")
    user: str = Field(default="root", description="SSH login username")
    identity_file: Optional[str] = Field(default=None, description="Path to private key file")
    tags: List[str] = Field(default_factory=list, description="Categorization tags (e.g. ['gpu', 'prod'])")
    description: Optional[str] = Field(default=None, description="Optional host description")

    def validate_alias(self) -> bool:
        """Verify alias contains only safe characters to prevent CLI injection."""
        return bool(_HOST_ALIAS_RE.match(self.alias))


class SSHCommandExecutionResult(BaseModel):
    """Result of an executed remote SSH command."""

    host_alias: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    is_timeout: bool = False
    is_blocked_high_risk: bool = False
    error_message: Optional[str] = None


class SFTPTransferResult(BaseModel):
    """Result of an SFTP file pull or push operation."""

    host_alias: str
    action: str  # "pull" | "push"
    remote_path: str
    local_path: str
    file_size_bytes: int = 0
    duration_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None


def parse_ssh_config_text(config_text: str) -> List[RemoteHostConfig]:
    """Parse standard OpenSSH config file text into structured RemoteHostConfig list.

    Handles Host, HostName, Port, User, IdentityFile directives with clean fallback.
    Ignores wildcards like Host * and comments.
    """
    hosts: List[RemoteHostConfig] = []
    current_alias: Optional[str] = None
    current_dict: Dict[str, Any] = {}

    def _flush_current() -> None:
        if current_alias and current_alias != "*" and "hostname" in current_dict:
            hosts.append(
                RemoteHostConfig(
                    alias=current_alias,
                    hostname=current_dict.get("hostname", current_alias),
                    port=int(current_dict.get("port", 22)),
                    user=current_dict.get("user", "root"),
                    identity_file=current_dict.get("identityfile"),
                )
            )

    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        if len(parts) < 2:
            continue

        key, val = parts[0].lower(), parts[1].strip().strip('"').strip("'")

        if key == "host":
            _flush_current()
            current_alias = val.split()[0] if " " in val else val
            current_dict = {}
        elif current_alias is not None:
            if key == "hostname":
                current_dict["hostname"] = val
            elif key == "port":
                try:
                    current_dict["port"] = int(val)
                except ValueError:
                    current_dict["port"] = 22
            elif key == "user":
                current_dict["user"] = val
            elif key == "identityfile":
                current_dict["identityfile"] = str(Path(val).expanduser())

    _flush_current()
    return hosts
