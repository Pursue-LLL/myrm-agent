"""Pydantic schemas for Snapshot Lag Aware Memory Freshness Suite (Item 157).

[INPUT]
- Session initialization payloads, memory write mutation requests, and lookup queries.

[OUTPUT]
- MemorySnapshotDigestDTO, SessionWriteDeltaDTO, SnapshotFreshnessStateDTO,
  DirectDiskReadHintDTO, and DeltaPatchBlockDTO.

[POS]
- Server-side DTO contracts for Item 157 SnapshotLagAwareMemoryFreshnessAndDiskVerificationContractSuite.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

WriteActionDTO = Literal["create", "update", "delete"]


class MemorySnapshotDigestDTO(BaseModel):
    """Cryptographic or monotonic digest tracking the version of injected memory context."""

    digest: str
    session_id: str
    created_at: str
    initial_items_count: int = 0


class InitSnapshotRequest(BaseModel):
    """Payload to initialize a session memory snapshot digest."""

    session_id: str
    initial_content: str = ""
    items_count: int = 0


class SessionWriteDeltaDTO(BaseModel):
    """Incremental fact mutated or committed during an ongoing multi-turn session."""

    key: str
    content: str
    turn_index: int = 0
    written_at: str = ""
    action: WriteActionDTO = "update"


class RecordWriteRequest(BaseModel):
    """Payload to record an ongoing memory write event to disk."""

    session_id: str
    key: str
    content: str
    turn_index: int = 0
    action: WriteActionDTO = "update"


class SnapshotFreshnessStateDTO(BaseModel):
    """Current staleness and dirty state of memory snapshot for an active session."""

    session_id: str
    snapshot_digest: str
    is_dirty: bool = False
    deltas: list[SessionWriteDeltaDTO] = Field(default_factory=list)
    latest_disk_version: int = 1


class DirectDiskReadHintDTO(BaseModel):
    """Contract hint prompting the agent to directly inspect persistent disk storage."""

    session_id: str
    hint_message: str
    affected_keys: list[str] = Field(default_factory=list)
    is_dirty: bool = False


class DeltaPatchBlockDTO(BaseModel):
    """Formatted incremental delta block appendable to system instructions without busting prompt cache."""

    header: str
    patches: list[str] = Field(default_factory=list)
    formatted_block: str = ""
