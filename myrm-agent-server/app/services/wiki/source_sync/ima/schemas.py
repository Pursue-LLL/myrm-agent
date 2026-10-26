"""Response contracts of the ima sync API.

[INPUT]
- .state::ImaKbSelection (POS: selected library)

[OUTPUT]
- ImaStatus / ImaItemCounts / ImaJobStatus / ImaItemView / ImaLibrary

[POS]
Typed shapes the frontend card renders. Counts and phases only; raw error text and technical detail never
leave the server, the UI maps ``reason`` codes to plain-language copy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .state import ImaKbSelection


class ImaLibrary(BaseModel):
    id: str
    name: str


class ImaItemCounts(BaseModel):
    total: int = 0
    synced: int = 0
    pending: int = 0
    failed: int = 0
    unsupported: int = 0
    too_large: int = 0
    blocked: int = 0
    dismissed: int = 0
    remote_deleted: int = 0
    duplicate: int = 0
    partial: int = 0


class ImaJobStatus(BaseModel):
    state: Literal["none", "active", "paused"] = "none"
    next_run_at: datetime | None = None


class ImaStatus(BaseModel):
    connected: bool = False
    account_hint: str = ""
    needs_reauth: bool = False
    knowledge_bases: list[ImaKbSelection]
    include_notes: bool = True
    job: ImaJobStatus
    phase: Literal["idle", "inventory", "fetch"] = "idle"
    backfill_complete: bool = False
    last_run_at: datetime | None = None
    last_error_kind: str = ""
    notes_unavailable: bool = False
    auto_compile: bool = False
    counts: ImaItemCounts
    total_chars: int = 0


class ImaItemView(BaseModel):
    title: str
    folder_path: str
    container_name: str
    media_kind: str
    status: str
    reason: str
    notes: list[str]
