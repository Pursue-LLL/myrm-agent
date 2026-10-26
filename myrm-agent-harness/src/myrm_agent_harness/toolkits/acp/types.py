"""Core type definitions for the ACP runtime system.

Defines the fundamental abstractions: RuntimeBackend Protocol, RuntimeEvent,
error codes, configuration, and permission types. All other ACP runtime modules
depend on this module.


[INPUT]
no - Base type definition module

[OUTPUT]
- RuntimeBackend: Runtime Backend abstract protocol
- DelegationPool: the pool surface a delegation caller needs (RuntimePool and host-side wrappers satisfy it)
- RuntimeEvent: Runtime Event type
- AcpErrorCode: ACP error enum
- ContinuityStatus: status_update statuses for a CLI conversation that could not be continued
- RuntimeConfig: Runtime configuration
- CliSessionRecord: a CLI-native session id bound to the working directory that created it
- CliSessionStore: protocol a host implements to keep CLI session records across process restarts
- PermissionMode: Permission pattern type
- PermissionDecision: Permission decision enum

[POS]
ACP runtime type definitions layer. Provides all ACP-related core abstractions and data
structures, serving as the foundation for the entire ACP module.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RuntimeEventType(StrEnum):
    """Event types emitted during a runtime turn."""

    TEXT_DELTA = "text_delta"
    REASONING_DELTA = "reasoning_delta"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    PERMISSION_REQUEST = "permission_request"
    USAGE_UPDATE = "usage_update"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    DONE = "done"


class AcpErrorCode(StrEnum):
    """Structured error codes for ACP runtime operations."""

    AUTH_FAILED = "auth_failed"
    BACKEND_NOT_FOUND = "backend_not_found"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    PROCESS_CRASHED = "process_crashed"
    MAX_TURNS = "max_turns"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ContinuityStatus(StrEnum):
    """``status_update`` statuses telling that the conversation a CLI agent recorded earlier is not continued."""

    SESSION_EXPIRED = "session_expired"
    WORKSPACE_CHANGED = "session_workspace_changed"

    @classmethod
    def of(cls, status: object) -> ContinuityStatus | None:
        """The continuity status that ``status`` stands for, or None for any other status."""
        try:
            return cls(status)
        except ValueError:
            return None


PermissionMode = Literal["safe", "ask", "allow_all", "bypass"]

BackendType = Literal["acp", "cli"]

BackendStatus = Literal["ready", "starting", "error", "stopped"]

# How a delegated backend authenticates with its model provider.
# - "subscription": the backend uses its own logged-in credentials (the user's
#   ChatGPT Plus / Claude Max / Gemini subscription persisted by the CLI itself);
#   provider API keys are stripped from the child environment so the CLI is forced
#   onto its subscription session and never silently falls back to metered API billing.
# - "api_key": the host injects a specific provider key via ``RuntimeConfig.env``;
#   usage is billed per token against that key.
AuthMode = Literal["subscription", "api_key"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AcpError:
    """Structured error with code, message, and retryable flag."""

    code: AcpErrorCode
    message: str
    retryable: bool = False
    details: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """A single event emitted during a runtime turn.

    For ``permission_request`` events, ``data["response_future"]`` contains an
    ``asyncio.Future[PermissionDecision]`` that the subscriber must resolve.
    """

    type: RuntimeEventType
    data: dict[str, object]
    session_id: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    """Declares what a RuntimeBackend supports."""

    supports_resume: bool = False
    supports_mcp: bool = False
    supports_streaming: bool = True
    supports_tools: bool = True


@dataclass(frozen=True, slots=True)
class BackendInfo:
    """Runtime-queryable metadata about a backend."""

    name: str
    version: str | None = None
    backend_type: BackendType = "acp"
    status: BackendStatus = "ready"
    capabilities: BackendCapabilities = field(default_factory=BackendCapabilities)
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    """Configuration for an MCP server to inject into a runtime."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Unified configuration for any RuntimeBackend."""

    backend_type: BackendType
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None
    timeout_seconds: int = 300
    permission_mode: PermissionMode = "allow_all"
    allowed_tools: list[str] = field(default_factory=list)
    auth_mode: AuthMode = "subscription"
    mcp_servers: list[McpServerConfig] = field(default_factory=list)
    max_response_chars: int = 50_000
    max_turns: int = 25
    description: str = ""


@dataclass(frozen=True, slots=True)
class CliSessionRecord:
    """A CLI-native session id bound to the working directory it was created in.

    Claude Code files a conversation under its project directory, and before v2.1.223 ``--resume <id>`` finds
    it only from that directory. A turn resumes a record only when it starts in the directory that created
    it, which holds for every version.
    """

    cli_session_id: str
    cwd: str


class PermissionDecision(StrEnum):
    """Possible outcomes for a permission request."""

    ALLOW_ONCE = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY_ONCE = "deny_once"
    DENY_ALWAYS = "deny_always"


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class RuntimeBackend(Protocol):
    """Unified interface for ACP and CLI agent backends.

    Implementations must support the full lifecycle: run_turn, cancel, resume,
    get_info, and close.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    @property
    def is_alive(self) -> bool: ...

    def run_turn(
        self,
        prompt: str,
        session_id: str,
        *,
        mcp_servers: list[McpServerConfig] | None = None,
    ) -> AsyncGenerator[RuntimeEvent]: ...

    async def cancel(self, session_id: str) -> None: ...

    async def resume(self, session_id: str) -> bool: ...

    async def get_info(self) -> BackendInfo: ...

    async def close(self) -> None: ...


class DelegationPool(Protocol):
    """What a caller needs to delegate turns to configured backends.

    ``RuntimePool`` satisfies it, and so can a host-side wrapper that adds concerns of its own
    (per-conversation turn serialization, pool lifetime) without subclassing the pool.
    """

    @property
    def available_backends(self) -> list[str]: ...

    def get_config(self, name: str) -> RuntimeConfig | None: ...

    def run_turn(
        self,
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
        mcp_servers: list[McpServerConfig] | None = None,
    ) -> AsyncGenerator[RuntimeEvent]: ...

    async def cancel(self, name: str, session_id: str) -> None: ...


class CliSessionStore(Protocol):
    """Durable home of ``CliSessionRecord`` keyed by harness session id; one store serves one conversation scope.

    A host implements it so CLI sessions survive a restart of the host process. The runtime awaits every call
    while a turn runs (a record is saved as soon as the CLI announces its session), so an implementation bounds
    its own latency; a call that raises is degraded by the runtime to a fresh CLI session and never fails a turn.
    A record is never deleted: the next session the CLI announces overwrites it.
    """

    async def load(self, session_id: str) -> CliSessionRecord | None: ...

    async def save(self, session_id: str, record: CliSessionRecord) -> None: ...


@runtime_checkable
class PermissionManager(Protocol):
    """Protocol for permission checking — framework provides default, business layer can replace."""

    async def check(
        self,
        tool_name: str,
        tool_input: dict[str, object],
        session_id: str,
    ) -> PermissionDecision: ...

    def record_approval(self, tool_name: str, session_id: str) -> None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_event(
    event_type: RuntimeEventType,
    session_id: str,
    **data: object,
) -> RuntimeEvent:
    """Convenience factory for creating RuntimeEvent instances."""
    return RuntimeEvent(type=event_type, data=data, session_id=session_id)


def create_permission_request(
    session_id: str,
    tool_name: str,
    tool_input: dict[str, object],
) -> tuple[RuntimeEvent, asyncio.Future[PermissionDecision]]:
    """Create a permission_request event with its response Future.

    Returns:
        A (event, future) tuple. The subscriber resolves the future with a
        PermissionDecision; the runtime awaits it.
    """
    future: asyncio.Future[PermissionDecision] = asyncio.get_running_loop().create_future()
    event = RuntimeEvent(
        type=RuntimeEventType.PERMISSION_REQUEST,
        data={
            "tool_name": tool_name,
            "tool_input": tool_input,
            "response_future": future,
        },
        session_id=session_id,
    )
    return event, future
