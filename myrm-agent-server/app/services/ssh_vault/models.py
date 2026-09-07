"""Data models for SSH Asset Vault and Remote Host Management.

Defines host configurations, probe results, and remote execution payloads.

[INPUT]
- pydantic::BaseModel, Field
- typing::Any, Dict, List, Optional, Literal

[OUTPUT]
- SSHHostConfig, SSHProbeResult, SSHCommandPayload, SSHCommandResult, SSHAssetSummary

[POS]
Core models for SSH vault domain in app/services/ssh_vault/.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SSHHostConfig(BaseModel):
    """Configuration definition for a single SSH target host."""

    host_alias: str = Field(..., description="Unique alias name from ssh config or user defined")
    hostname: str = Field(..., description="Target server IP or domain name")
    port: int = Field(default=22, description="SSH connection port")
    user: str = Field(default="root", description="Login username")
    identity_file: Optional[str] = Field(default=None, description="Path to identity private key file")
    tags: List[str] = Field(default_factory=list, description="Categorization tags (e.g. gpu, prod, test)")
    description: Optional[str] = Field(default=None, description="Human readable description")


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
    timeout_seconds: int = Field(default=60, description="Max execution timeout in seconds")
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


class SSHAssetSummary(BaseModel):
    """Aggregated summary of available SSH hosts."""

    total_hosts: int = Field(..., description="Total configured hosts")
    hosts: List[SSHHostConfig] = Field(default_factory=list, description="List of host configs")
    config_source: str = Field(default="~/.ssh/config", description="Source of SSH configurations")
