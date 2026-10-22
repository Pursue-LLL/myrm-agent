"""[INPUT] Pydantic models for Agent-Owned operations REST APIs.
[OUTPUT] Strong DTOs: AgentRegisterRequest, AgentRosterResponse, ResolveCapabilityRequest, ResolveCapabilityResponse, AgentScopedErrorDTO.
[POS] Public schema models for Agent-Owned multi-agent operations fabric.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AgentProviderConfigDTO(BaseModel):
    """Provider configuration owned by a specific agent instance."""

    provider_name: str = Field(..., description="Provider backend identifier (e.g. openai, anthropic, deepseek)")
    model_name: str = Field(..., description="Target model identifier (e.g. deepseek-chat, claude-3-5-sonnet)")
    api_base: Optional[str] = Field(default=None, description="Optional custom base URL for private API or proxy")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, description="Maximum token generation limit")
    timeout_seconds: float = Field(default=60.0, gt=0.0, description="Per-request invocation timeout in seconds")


class AgentRegisterRequest(BaseModel):
    """Payload to register an agent instance with dedicated context in the fabric."""

    agent_id: str = Field(..., description="Unique agent identifier")
    role: str = Field(default="general_worker", description="Functional role of the agent")
    parent_agent_id: Optional[str] = Field(default=None, description="Parent/supervisor agent ID")
    session_id: str = Field(default="", description="Chat session identifier")
    provider_config: AgentProviderConfigDTO = Field(..., description="Agent-owned provider setup")
    capabilities: List[str] = Field(default_factory=list, description="Declared capability tags")
    allowlist: List[str] = Field(default_factory=list, description="Allowed tool or action identifiers")


class AgentScopedErrorDTO(BaseModel):
    """Representation of an operation failure isolated to an agent."""

    error_id: str = Field(..., description="Unique error record identifier")
    agent_id: str = Field(..., description="Originating agent identifier")
    operation: str = Field(..., description="Operation being executed during failure")
    error_type: str = Field(..., description="Categorized error class name")
    message: str = Field(..., description="Sanitized diagnostic error message")
    timestamp: float = Field(default_factory=time.time, description="Epoch timestamp of occurrence")
    fatal: bool = Field(default=False, description="Whether this halted the agent execution")
    context: Dict[str, str] = Field(default_factory=dict, description="Operational metadata without global session leakage")


class AgentRosterEntryDTO(BaseModel):
    """Standardized list-form roster representation of a registered agent."""

    agent_id: str = Field(..., description="Unique agent identifier")
    role: str = Field(..., description="Functional role of the agent")
    parent_agent_id: Optional[str] = Field(default=None, description="Immediate supervisor/orchestrator ID if delegated")
    session_id: str = Field(default="", description="Chat session identifier")
    provider_model: str = Field(..., description="Model string owned by the agent")
    capabilities: List[str] = Field(default_factory=list, description="Declared capability tags")
    allowlist: List[str] = Field(default_factory=list, description="Allowed tool or action identifiers")
    error_count: int = Field(default=0, description="Number of isolated errors in the agent's stack")
    is_healthy: bool = Field(default=True, description="Whether the agent is currently free of fatal errors")


class AgentRosterResponse(BaseModel):
    """List-form roster of registered agents."""

    agents: List[AgentRosterEntryDTO] = Field(default_factory=list, description="List of registered agent roster entries")
    total_count: int = Field(default=0, description="Total count of agents in roster")


class ResolveCapabilityRequest(BaseModel):
    """Request payload to test capability alignment against an agent's allowlist."""

    target_capability: str = Field(..., description="Target capability or tool name to resolve")


class ResolveCapabilityResponse(BaseModel):
    """Resolution verdict for an agent capability query."""

    agent_id: str = Field(..., description="Queried agent identifier")
    target_capability: str = Field(..., description="Evaluated capability name")
    is_allowed: bool = Field(..., description="Whether capability is allowed under agent's owned allowlist")


class RecordErrorRequest(BaseModel):
    """Manual or simulated error injection into an agent's isolated error stack."""

    operation: str = Field(..., description="Operation where the error occurred")
    error_type: str = Field(..., description="Error class name")
    message: str = Field(..., description="Diagnostic error message")
    fatal: bool = Field(default=False, description="Whether this is a fatal failure")
    context: Optional[Dict[str, str]] = Field(default=None, description="Diagnostic metadata")
