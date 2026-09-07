"""Data models and value objects for Host Assets and Remote SSH/SFTP Management.

[INPUT]
- Pydantic BaseModel, Field, SecretStr
- Enum definitions

[OUTPUT]
- AuthType, HostAsset, HostAssetCreate, HostAssetUpdate, SSHCommandRequest, SSHCommandResponse, SFTPFileEntry, SFTPTransferRequest, SFTPTransferResponse

[POS]
Data structures in app/services/host_assets/models.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class AuthType(str, Enum):
    """Authentication mechanism for SSH connections."""
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"
    AGENT = "agent"


class HostAssetBase(BaseModel):
    """Base definition of a remote host asset."""
    alias: str = Field(..., description="Unique user-friendly alias/name for the host (e.g. gpu-node-1)")
    hostname: str = Field(..., description="IP address or domain name")
    port: int = Field(default=22, ge=1, le=65535, description="SSH port")
    username: str = Field(..., description="Login username")
    auth_type: AuthType = Field(default=AuthType.PRIVATE_KEY, description="Authentication type")
    description: str = Field(default="", description="Optional asset description or tags")


class HostAssetCreate(HostAssetBase):
    """Payload for registering a new host asset."""
    password: str | None = Field(default=None, description="Plaintext password (encrypted before storage)")
    private_key: str | None = Field(default=None, description="Plaintext PEM/OpenSSH private key (encrypted before storage)")
    passphrase: str | None = Field(default=None, description="Optional key passphrase")


class HostAssetUpdate(BaseModel):
    """Payload for updating an existing host asset."""
    alias: str | None = None
    hostname: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    auth_type: AuthType | None = None
    description: str | None = None
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None


class HostAsset(HostAssetBase):
    """Persisted host asset entity (with sanitized secrets)."""
    id: str = Field(..., description="Unique UUID for the host asset")
    has_password: bool = Field(default=False, description="Whether a password is configured")
    has_private_key: bool = Field(default=False, description="Whether a private key is configured")
    encrypted_secret: str = Field(default="", description="Encrypted credentials payload")
    created_at: float = Field(..., description="Unix timestamp of creation")
    updated_at: float = Field(..., description="Unix timestamp of last update")


class SSHCommandRequest(BaseModel):
    """Request to execute a command on a remote host asset."""
    host_id_or_alias: str = Field(..., description="Target host UUID or alias")
    command: str = Field(..., description="Shell command to execute on the remote machine")
    timeout_seconds: int = Field(default=30, ge=1, le=300, description="Execution timeout in seconds")
    working_dir: str | None = Field(default=None, description="Remote directory to execute in")


class SSHCommandResponse(BaseModel):
    """Result of a remote SSH command execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: int
    host_alias: str
    error_message: str | None = None


class SFTPFileEntry(BaseModel):
    """Metadata of a file/directory on a remote host."""
    filename: str
    path: str
    is_dir: bool
    size_bytes: int
    modified_time: float
    permissions: str


class SFTPTransferRequest(BaseModel):
    """Request for uploading or downloading a file via SFTP."""
    host_id_or_alias: str
    direction: Literal["upload", "download"]
    local_path: str
    remote_path: str


class SFTPTransferResponse(BaseModel):
    """Result of an SFTP transfer operation."""
    success: bool
    bytes_transferred: int
    remote_path: str
    local_path: str
    elapsed_time_ms: int
    error_message: str | None = None
