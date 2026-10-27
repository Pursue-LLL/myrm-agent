"""Doubles for the cron-entry tests of the ima sync: what the slice runner is wired to, and what they recorded."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.source_sync.ima.context import SyncContext
from app.services.wiki.source_sync.ima.engine import SliceOutcome
from app.services.wiki.source_sync.ima.models import ImaCredentials
from app.services.wiki.source_sync.ima.state import (
    ImaKbSelection,
    ImaSyncConfig,
    ImaSyncState,
    save_ima_config,
    save_ima_state,
)

LLM = cast(BaseChatModel, object())
CREDENTIALS = ImaCredentials(client_id="cid", api_key="key")
# How often the fixture makes a running slice ask whether its sync is still wanted.
POLL_S = 0.01


def job_id(agent_id: str | None) -> str:
    return f"job:{agent_id}"


@dataclass
class Harness:
    contexts: list[SyncContext] = field(default_factory=list)
    outcome: SliceOutcome = field(
        default_factory=lambda: SliceOutcome(finished=False, retry_after_s=5.0, published=0, generation_total=0)
    )
    snapshots: int = 0
    dedups: int = 0
    credentials: ImaCredentials | None = CREDENTIALS
    auto_compile: bool = True
    gate: asyncio.Event | None = None
    events: list[str] = field(default_factory=list)
    publish: dict[str, str] = field(default_factory=dict)
    slice_error: Exception | None = None
    scan_completes: bool = True
    # Jobs the user paused or removed.
    paused: set[str] = field(default_factory=set)
    # Raised when the running slice asks whether its sync is still wanted.
    mandate_read_error: Exception | None = None
    # The user pauses right after the cron job was read for admission.
    pause_after_admission: bool = False

    def pause(self, agent_id: str | None) -> None:
        self.paused.add(job_id(agent_id))

    def release(self) -> None:
        """Let the slices held at the gate go on."""
        if self.gate is not None:
            self.gate.set()


class FakeCompiler:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def enqueue_file(self, file_path: Path) -> None:
        self._events.append(f"enqueue:{file_path.name}")


class FakeArchiver:
    def __init__(self, root: Path, events: list[str]) -> None:
        from myrm_agent_harness.toolkits.wiki import WikiStructure

        self._structure = WikiStructure(base_dir=root)
        self._compiler = FakeCompiler(events)


async def configure(
    ima_db: async_sessionmaker[AsyncSession],
    *,
    backfill_complete: bool = False,
    notes: bool = True,
    libraries: tuple[ImaKbSelection, ...] = (),
    agent_id: str | None = None,
) -> None:
    async with ima_db() as db:
        await save_ima_config(db, ImaSyncConfig(knowledge_bases=list(libraries), include_notes=notes), agent_id=agent_id)
        await save_ima_state(db, ImaSyncState(backfill_complete=backfill_complete), agent_id=agent_id)
