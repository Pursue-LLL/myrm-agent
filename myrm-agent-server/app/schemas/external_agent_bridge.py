"""[INPUT] None.
[OUTPUT] Pydantic models and request/response DTOs for Heterogeneous External Agent Bridge & CLI Adapter.
[POS] HTTP schema validation layer for external CLI agent bridge endpoints.
"""

from __future__ import annotations

import time
from typing import Literal

from myrm_agent_harness.agent.sub_agents.cli_adapter.types import (
    ExternalAgentKind,
    ProcessLaneStatus,
)
from pydantic import BaseModel, Field


class ExternalAgentConfigDTO(BaseModel):
    """Configuration descriptor for spawning an external CLI agent lane."""

    agent_id: str = Field(..., description="Unique identifier of external CLI agent")
    name: str = Field(..., description="Display name of the CLI agent")
    kind: ExternalAgentKind = Field(..., description="Kind/category of the CLI agent")
    command: str = Field(..., description="Executable path or command name in PATH")
    args: list[str] = Field(default_factory=list, description="Base command-line arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Custom environment variable overrides")
    cwd: str | None = Field(default=None, description="Working directory for spawned process")
    max_turns: int = Field(default=10, ge=1, le=100, description="Maximum allowed conversation turns")
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0, description="Process execution timeout in seconds")
    max_budget_usd: float = Field(default=1.0, ge=0.0, description="Safety budget limit in USD")
    expected_model: str | None = Field(default=None, description="Target backend model identifier")


class RegisterExternalAgentRequest(BaseModel):
    """Payload to register or update an external CLI agent profile."""

    agent_id: str = Field(..., description="Unique agent identifier (e.g. claude-code-lane-1)")
    name: str = Field(..., description="Display name for UI/CLI lane")
    kind: ExternalAgentKind = Field(default=ExternalAgentKind.GENERIC_STDIO, description="Kind of CLI agent")
    command: str = Field(..., description="CLI binary command or path")
    args: list[str] = Field(default_factory=list, description="Default CLI flags/arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    cwd: str | None = Field(default=None, description="Execution directory")
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0, description="Process timeout in seconds")
    expected_model: str | None = Field(default=None, description="Expected model name")


class ProcessExecutionRequestDTO(BaseModel):
    """Input payload dispatched to an external CLI agent process."""

    execution_id: str | None = Field(default=None, description="Optional custom execution ID")
    input_text: str = Field(..., description="Task prompt or standard input passed to CLI")
    turn_index: int = Field(default=1, ge=1, description="Current turn number in the lane")
    extra_args: list[str] = Field(default_factory=list, description="Supplemental invocation flags")


class ProcessReceiptDTO(BaseModel):
    """Cryptographically verifiable execution receipt capturing CLI output and exit facts."""

    execution_id: str = Field(..., description="Execution unique ID")
    agent_id: str = Field(..., description="Agent identifier")
    kind: ExternalAgentKind = Field(..., description="Agent kind")
    status: ProcessLaneStatus = Field(..., description="Terminal status of the process lane")
    exit_code: int | None = Field(..., description="Process exit return code")
    duration_ms: int = Field(..., description="Total execution duration in milliseconds")
    stdout_summary: str = Field(..., description="Sanitized stdout text")
    stderr_summary: str = Field(..., description="Sanitized stderr text")
    receipt_hash: str = Field(..., description="SHA-256 verifiable receipt hash")
    created_at: float = Field(default_factory=time.time, description="Creation timestamp")


class ExternalAgentProbeResponse(BaseModel):
    """Probe result verifying CLI binary availability and execution permissions."""

    agent_id: str = Field(..., description="Agent ID probed")
    is_healthy: bool = Field(..., description="Whether binary is resolvable and executable")
    command: str = Field(..., description="Configured command path")


class ExternalAgentListResponse(BaseModel):
    """List of all registered external CLI agents."""

    agents: list[ExternalAgentConfigDTO] = Field(default_factory=list, description="Registered external agents")
    total: int = Field(..., description="Total number of registered external agents")


class ExternalAgentReceiptsResponse(BaseModel):
    """Execution receipts history for a given external CLI agent."""

    agent_id: str = Field(..., description="Target external agent ID")
    receipts: list[ProcessReceiptDTO] = Field(default_factory=list, description="Ordered receipt history")
    total: int = Field(..., description="Total receipts count")


class OperationStatusResponse(BaseModel):
    """General operation status reply."""

    success: bool = Field(..., description="Whether operation succeeded")
    action: Literal["registered", "unregistered", "executed"] = Field(..., description="Action performed")
    detail: str | None = Field(default=None, description="Supplemental description")
