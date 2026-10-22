"""Pydantic V2 DTO schemas for Heterogeneous External Agent Adapter and Subagent Bundle Manager."""

from __future__ import annotations

from enum import StrEnum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ExternalAgentTypeEnum(StrEnum):
    """Supported external agent types."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    GEMINI_CLI = "gemini_cli"
    CUSTOM = "custom"


class BundleExecutionModeEnum(StrEnum):
    """Execution sandbox mode for external subagents."""

    NATIVE_CLI = "native_cli"
    DOCKER_CONTAINER = "docker_container"
    SANDBOX_ISOLATED = "sandbox_isolated"


class SubagentInstanceStatusEnum(StrEnum):
    """Lifecycle status of an external subagent instance."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class ExternalBundleProfileSpecDTO(BaseModel):
    """Packaging specification for a third-party CLI agent."""

    bundle_id: str = Field(..., description="Unique bundle identifier (e.g. subagent-codex)")
    agent_type: ExternalAgentTypeEnum = Field(..., description="Target agent family")
    display_name: str = Field(..., description="Human-friendly label")
    description: str = Field(..., description="Specialty description of the external agent")
    binary_name: str = Field(..., description="CLI executable command name (e.g. codex, claude)")
    command_template: str = Field(default="{binary} --print --prompt '{prompt}'", description="Execution template")
    capabilities: List[str] = Field(default_factory=list, description="Claimed capabilities")
    env_whitelist: List[str] = Field(default_factory=list, description="Whitelisted environment variables")
    allowed_roots: List[str] = Field(default_factory=list, description="Permitted directory path scopes")
    execution_mode: BundleExecutionModeEnum = Field(default=BundleExecutionModeEnum.SANDBOX_ISOLATED)
    max_concurrency: int = Field(default=5, ge=1, le=20, description="Max parallel instances for this bundle")
    is_installed: bool = Field(default=False, description="Whether executable was detected on host path")
    version: str = Field(default="1.0.0", description="Reported or detected version")


class SubagentInstanceRecordDTO(BaseModel):
    """State record of an instantiated external subagent worker."""

    instance_id: str = Field(..., description="Unique instance ID")
    bundle_id: str = Field(..., description="Bundle specification used")
    session_id: str = Field(..., description="Parent chat/session ID")
    role_label: str = Field(..., description="Task role label")
    status: SubagentInstanceStatusEnum = Field(default=SubagentInstanceStatusEnum.PENDING)
    pid: int = Field(default=0, description="OS process ID")
    task_prompt: str = Field(..., description="Dispatched prompt or instruction")
    target_workdir: str = Field(..., description="Effective working directory for this instance")
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    exit_code: Optional[int] = None
    stdout_chunks: List[str] = Field(default_factory=list, description="Aggregated stdout stream lines")
    artifacts: List[Dict[str, str]] = Field(default_factory=list, description="Materialized artifacts/diffs")
    error: Optional[str] = None


class BatchDispatchTaskDTO(BaseModel):
    """Single subagent task specification in a batch dispatch request."""

    bundle_id: str = Field(..., description="Bundle ID to instantiate (e.g. subagent-codex)")
    role_label: str = Field(..., description="Role label for this subagent instance")
    task_prompt: str = Field(..., description="Specific goal or instruction")
    target_subdir: str = Field(default="", description="Optional workspace subdirectory scope")
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0, description="Execution timeout limit")


class SingleDispatchRequestDTO(BaseModel):
    """Request payload to dispatch a single external subagent."""

    task: BatchDispatchTaskDTO = Field(..., description="Task specification")
    workspace_root: Optional[str] = Field(default=None, description="Optional custom workspace root override")


class BatchDispatchRequestDTO(BaseModel):
    """Request payload to concurrently dispatch multiple subagents."""

    tasks: List[BatchDispatchTaskDTO] = Field(..., min_length=1, description="List of subagent tasks to run in parallel")
    workspace_root: Optional[str] = Field(default=None, description="Optional custom workspace root override")


class BatchDispatchResultDTO(BaseModel):
    """Response returned upon batch multiplexed dispatch."""

    batch_id: str = Field(..., description="Unique batch dispatch ID")
    session_id: str = Field(..., description="Target session ID")
    total_dispatched: int = Field(..., description="Number of instances concurrently launched")
    dispatched_instances: List[SubagentInstanceRecordDTO] = Field(default_factory=list)


class ProbeBundleResponseDTO(BaseModel):
    """Response returned upon host environment probe for a bundle binary."""

    bundle_id: str
    binary_name: str
    is_installed: bool
    version: str


class TerminateInstanceRequestDTO(BaseModel):
    """Request payload to terminate an active instance."""

    reason: str = Field(default="user_cancelled", description="Termination justification")


class TerminateInstanceResponseDTO(BaseModel):
    """Response returned upon terminating an instance."""

    instance_id: str
    terminated: bool
    status: SubagentInstanceStatusEnum
    error: Optional[str] = None


class BundleCatalogResponseDTO(BaseModel):
    """Catalog response containing registered bundles and system capacity."""

    total_bundles: int
    bundles: List[ExternalBundleProfileSpecDTO] = Field(default_factory=list)
