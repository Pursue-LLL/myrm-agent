"""Data models for remote host asset management and agent operations.

[INPUT]
- pydantic::BaseModel, Field
- typing::Dict, List, Optional, Literal

[OUTPUT]
- RemoteHostConfig: Complete connection metadata for a single remote host.
- RemoteHostSummary: Lightweight safe summary for UI presentation and listing.
- HostAssetImportResult: Batch import results from SSH configuration.

[POS]
Data models in app/services/remote_host/.
"""

from __future__ import annotations

import time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RemoteHostConfig(BaseModel):
    """Complete host configuration for remote operations."""

    alias: str = Field(..., description="Unique human-readable host alias (e.g. 'gpu-cluster', 'prod-web')")
    hostname: str = Field(..., description="IP address or domain name of remote server")
    port: int = Field(default=22, description="SSH port number")
    username: str = Field(default="root", description="SSH login username")
    auth_type: Literal["key", "agent", "password"] = Field(default="agent", description="Authentication mode")
    identity_file: Optional[str] = Field(default=None, description="Path to SSH private key on disk")
    description: Optional[str] = Field(default=None, description="Optional host description or environment note")
    tags: List[str] = Field(default_factory=list, description="Categorization tags (e.g. ['prod', 'gpu', 'k8s'])")
    created_at: float = Field(default_factory=time.time, description="Creation timestamp")
    is_active: bool = Field(default=True, description="Whether host is enabled for agent dispatch")


class RemoteHostSummary(BaseModel):
    """Sanitized host summary safe for public and LLM listing."""

    alias: str
    hostname: str
    port: int
    username: str
    auth_type: str
    tags: List[str]
    is_active: bool


class HostAssetImportResult(BaseModel):
    """Summary of batch SSH config import operation."""

    total_discovered: int
    imported: List[str]
    skipped: List[str]
    errors: List[str] = Field(default_factory=list)
