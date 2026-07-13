"""Typed structures for wave orchestrator state.

[INPUT]
- None (stdlib typing only)

[OUTPUT]
- WaveRecord / LeaseRecord / Lane / OrchestratorState

[POS]
Schema types for immutable test wave JSON state.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

WaveStatus = Literal["open", "closed", "drifted"]
LeaseStatus = Literal["active", "released", "expired"]
Lane = Literal["READ", "RESOURCE_WRITE", "GLOBAL_WRITE", "LIVE_AGENT", "STACK_WRITE"]
ResourceKind = Literal["chat", "project", "agent", "cron", "file", "kanban_board", "kanban_task"]
ResourceStatus = Literal["active", "cleaned", "failed"]

VALID_LANES: frozenset[Lane] = frozenset(
    {"READ", "RESOURCE_WRITE", "GLOBAL_WRITE", "LIVE_AGENT", "STACK_WRITE"}
)
VALID_RESOURCE_KINDS: frozenset[ResourceKind] = frozenset(
    {"chat", "project", "agent", "cron", "file", "kanban_board", "kanban_task"}
)


class WaveRecord(TypedDict):
    waveId: str
    status: WaveStatus
    runtimeId: str
    openedAt: str
    closedAt: str | None
    openedBy: str


class LeaseRecord(TypedDict):
    leaseId: str
    waveId: str
    agentId: str
    lane: Lane
    runtimeId: str
    namespace: NotRequired[str]
    createdAt: str
    expiresAt: str
    lastHeartbeatAt: str
    status: LeaseStatus
    pageId: NotRequired[str]
    pageUrl: NotRequired[str]
    contextId: NotRequired[str]


class ResourceRecord(TypedDict):
    resourceId: str
    leaseId: str
    namespace: str
    agentId: str
    kind: ResourceKind
    ref: str
    createdAt: str
    status: ResourceStatus
    cleanedAt: NotRequired[str]
    lastError: NotRequired[str]


class OrchestratorState(TypedDict):
    version: int
    wave: WaveRecord | None
    leases: list[LeaseRecord]
    resources: list[ResourceRecord]
