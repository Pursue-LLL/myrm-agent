"""Data models for SSH Asset Vault and Remote Host Management.

Defines host configurations, probe results, execution results, and SFTP transfer structures.

[INPUT]
- pydantic::BaseModel, Field
- typing::Any, Dict, List, Optional
- re::Pattern

[OUTPUT]
- SSHHostConfig, SSHProbeResult, SSHCommandPayload, SSHCommandResult, SFTPTransferResult, SSHAssetSummary

[POS]
Core models for SSH vault domain in app/services/ssh_vault/.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

_HOST_ALIAS_RE = re.compile(r"^[a-zA-Z0-9_\.\-]+$")


class SSHHostConfig(BaseModel):
    """Configuration definition for a single SSH target host."""

    host_alias: str = Field(..., description="Unique alias name from ssh config or user defined")
    hostname: str = Field(..., description="Target server IP or domain name")
    port: int = Field(default=22, ge=1, le=65535, description="SSH connection port")
    user: str = Field(default="root", description="Login username")
    identity_file: Optional[str] = Field(default=None, description="Path to identity private key file")
    tags: List[str] = Field(default_factory=list, description="Categorization tags (e.g. gpu, prod, test)")
    description: Optional[str] = Field(default=None, description="Human readable description")

    def validate_alias(self) -> bool:
        """Verify alias contains only safe characters to prevent CLI injection."""
        return bool(_HOST_ALIAS_RE.match(self.host_alias))


class SSHProbeResult(BaseModel):
    """Result of an SSH connection health check / probe."""

    host_alias: str = Field(..., description="Host alias probed")
    is_reachable: bool = Field(..., description="Whether host is reachable via TCP/SSH")
    latency_ms: Optional[float] = Field(default=None, description="Ping/connect latency in milliseconds")
    os_info: Optional[str] = Field(default=None, description="Remote OS snapshot if authenticated")
    error_message: Optional[str] = Field(default=None, description="Failure reason if probe failed")


class SSHCommandPayload(BaseModel):
    """Request payload to dispatch a remote command via SSH."""

    host_alias: str = Field(..., description="Target host alias")
    command: str = Field(..., description="Shell command to execute on remote server")
    timeout_seconds: float = Field(default=30.0, description="Max execution timeout in seconds")
    allow_high_risk: bool = Field(default=False, description="Whether to bypass high-risk command guard")
    working_directory: Optional[str] = Field(default=None, description="Optional working directory on remote")


class SSHCommandResult(BaseModel):
    """Result of an executed remote SSH command."""

    host_alias: str = Field(..., description="Target host alias")
    command: str = Field(..., description="Command that was executed")
    exit_code: int = Field(..., description="Process exit code")
    stdout: str = Field(default="", description="Raw or distilled standard output")
    stderr: str = Field(default="", description="Standard error output")
    duration_ms: int = Field(default=0, description="Execution duration in milliseconds")
    distilled: bool = Field(default=False, description="Whether log was processed by distiller")
    is_timeout: bool = Field(default=False, description="Whether execution exceeded timeout")
    is_blocked_high_risk: bool = Field(default=False, description="Whether command was blocked by safety policy")
    error_message: Optional[str] = Field(default=None, description="Detailed error message if failed")


class SFTPTransferResult(BaseModel):
    """Result of an SFTP file pull or push operation."""

    host_alias: str = Field(..., description="Target host alias")
    action: str = Field(..., description="Transfer direction ('pull' | 'push')")
    remote_path: str = Field(..., description="Remote filesystem path")
    local_path: str = Field(..., description="Local filesystem path")
    file_size_bytes: int = Field(default=0, description="Transferred file size in bytes")
    duration_ms: int = Field(default=0, description="Transfer duration in milliseconds")
    success: bool = Field(default=True, description="Whether transfer succeeded")
    error_message: Optional[str] = Field(default=None, description="Error details if transfer failed")


class SSHAssetSummary(BaseModel):
    """Aggregated summary of available SSH hosts."""

    total_hosts: int = Field(..., description="Total configured hosts")
    hosts: List[SSHHostConfig] = Field(default_factory=list, description="List of host configs")
    config_source: str = Field(default="~/.ssh/config", description="Source of SSH configurations")
