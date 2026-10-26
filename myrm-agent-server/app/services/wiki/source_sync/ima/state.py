"""Persisted ima sync configuration and resumable run state (agent-scoped UserConfig).

[INPUT]
- app.services.wiki._userconfig_scoped (POS: shared agent-scoped UserConfig persistence)

[OUTPUT]
- ImaSyncConfig / ImaSyncState / ImaWalkTask / ImaKbSelection models
- load_ima_config / save_ima_config / load_ima_state / save_ima_state

[POS]
``wikiImaSync`` holds what the user chose (libraries, notes toggle); ``wikiImaSyncState`` holds the resumable
inventory cursors so a restart or time-boxed slice continues where it stopped instead of rescanning. Cursors are
opaque ima tokens stored as received: a length cap would turn one unusually long token into state that fails to
reload, which resets the whole sync.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wiki._userconfig_scoped import load_scoped_userconfig, save_scoped_userconfig

from .identity import NOTES_LANE

CONFIG_KEY = "wikiImaSync"
STATE_KEY = "wikiImaSyncState"


class ImaKbSelection(BaseModel):
    id: str = Field(max_length=128)
    name: str = Field(max_length=256)


class ImaSyncConfig(BaseModel):
    knowledge_bases: list[ImaKbSelection] = Field(default_factory=list, max_length=50)
    include_notes: bool = True

    @property
    def containers(self) -> list[str]:
        """Ledger containers this configuration imports; rows of deselected libraries are left untouched, never counted."""
        return [*(kb.id for kb in self.knowledge_bases), *([NOTES_LANE] if self.include_notes else [])]

    def fingerprint(self) -> str:
        """Identity of what is imported; a run restarts its inventory when this differs from the one it started with."""
        scope = ",".join(sorted(kb.id for kb in self.knowledge_bases)) + f"|{int(self.include_notes)}"
        return hashlib.sha256(scope.encode()).hexdigest()[:16]


class ImaWalkTask(BaseModel):
    """One pending page of the knowledge-base tree walk."""

    kb_id: str = Field(max_length=128)
    kb_name: str = Field(max_length=256)
    folder_id: str = Field(default="", max_length=256)
    folder_path: list[str] = Field(default_factory=list, max_length=16)
    cursor: str = ""


class ImaSyncState(BaseModel):
    phase: Literal["idle", "inventory", "fetch"] = "idle"
    generation: int = 0
    queue: list[ImaWalkTask] = Field(default_factory=list)
    # Notes lane position: "" means the first page is next, None means the lane is not being walked.
    notes_cursor: str | None = None
    failed_containers: list[str] = Field(default_factory=list)
    inventory_pages: int = 0
    generation_published: int = 0
    failure_streak: int = 0
    backfill_complete: bool = False
    last_run_at: datetime | None = None
    last_error_kind: str = Field(default="", max_length=24)
    needs_reauth: bool = False
    config_fingerprint: str = Field(default="", max_length=16)


async def load_ima_config(db: AsyncSession, *, agent_id: str | None) -> ImaSyncConfig:
    return await load_scoped_userconfig(
        db,
        config_key=CONFIG_KEY,
        model=ImaSyncConfig,
        agent_id=agent_id,
        legacy_keys=(),
        invalid_log_label=CONFIG_KEY,
    )


async def save_ima_config(db: AsyncSession, config: ImaSyncConfig, *, agent_id: str | None) -> ImaSyncConfig:
    return await save_scoped_userconfig(
        db, config_key=CONFIG_KEY, model=ImaSyncConfig, value=config, agent_id=agent_id, legacy_keys=()
    )


async def load_ima_state(db: AsyncSession, *, agent_id: str | None) -> ImaSyncState:
    return await load_scoped_userconfig(
        db,
        config_key=STATE_KEY,
        model=ImaSyncState,
        agent_id=agent_id,
        legacy_keys=(),
        invalid_log_label=STATE_KEY,
    )


async def save_ima_state(db: AsyncSession, state: ImaSyncState, *, agent_id: str | None) -> ImaSyncState:
    return await save_scoped_userconfig(
        db, config_key=STATE_KEY, model=ImaSyncState, value=state, agent_id=agent_id, legacy_keys=()
    )
