"""Cron entry of the ima sync: one slice per call, single-flight per agent.

[INPUT]
- .engine::run_slice (POS: time-boxed slice)
- .job::is_job_active (POS: the cron job is the user's switch for the sync)
- .credentials / .state / .ledger (POS: stored credentials, resumable state, per-item ledger)
- app.services.wiki.vault (POS: vault path and archiver SSOT)
- app.services.wiki.source_sync.deferred_enqueue (POS: holds auto-compile enqueue until the duplicate scan has run)

[OUTPUT]
- ImaJobOutcome / run_ima_sync_job / stop_running_slice / stop_running_slices

[POS]
Bridges the ``__wiki_ima_sync__`` router command to the engine. It owns the wiring the engine must not know
about: credentials, the wiki archiver, whether published files may be queued for compilation (only after the
slice's duplicate scan has had its say), and the post-publish ingest snapshot and incremental dedup. It also
knows which slices are running, so the user's pause or disconnect ends them at their next item instead of when
the time budget runs out.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from langchain_core.language_models import BaseChatModel

from app.database.connection import get_session
from app.services.wiki.agent_scope import normalize_agent_scope
from app.services.wiki.dedup_runner import run_post_sync_dedup_scan
from app.services.wiki.source_sync.config_store import load_wiki_source_sync_config
from app.services.wiki.source_sync.deferred_enqueue import DeferredCompileEnqueue
from app.services.wiki.vault import get_wiki_archiver

from .client import ImaClient
from .context import SyncContext
from .credentials import load_credentials
from .engine import SLICE_BUDGET_S, SliceOutcome, run_slice
from .job import is_job_active
from .ledger import ImaLedger
from .state import load_ima_config, load_ima_state
from .transport import ImaTransport

SILENT = "[SILENT]"
_slice_locks: dict[str, asyncio.Lock] = {}
# Stop signals of the slices running now, by scope: the user's pause or disconnect sets them.
_running: dict[str, asyncio.Event] = {}


@dataclass(frozen=True, slots=True)
class ImaJobOutcome:
    summary_text: str
    skipped: bool = False
    retry_at: datetime | None = None


_NOTHING_TO_DO = ImaJobOutcome(SILENT, skipped=True)


def stop_running_slice(agent_id: str | None) -> None:
    """End the agent's running slice at its next item; nothing happens when none is running."""
    stop = _running.get(normalize_agent_scope(agent_id))
    if stop is not None:
        stop.set()


def stop_running_slices() -> None:
    """End every agent's running slice."""
    for stop in _running.values():
        stop.set()


async def run_ima_sync_job(*, llm: BaseChatModel, agent_id: str | None) -> ImaJobOutcome:
    scope = normalize_agent_scope(agent_id)
    lock = _slice_locks.setdefault(scope, asyncio.Lock())
    if lock.locked():
        return _NOTHING_TO_DO
    async with lock:
        stop = _running[scope] = asyncio.Event()
        try:
            # The user may have paused or removed the job after it fired. Asked once the slice is registered: a pause
            # that lands later finds the slice, one that landed earlier shows here.
            if not await is_job_active(agent_id):
                return _NOTHING_TO_DO
            return await _run_slice_locked(llm, agent_id, stop)
        finally:
            del _running[scope]


async def _run_slice_locked(llm: BaseChatModel, agent_id: str | None, stop: asyncio.Event) -> ImaJobOutcome:
    credentials = await load_credentials()
    if credentials is None:
        return _NOTHING_TO_DO
    async with get_session() as db:
        config = await load_ima_config(db, agent_id=agent_id)
        state = await load_ima_state(db, agent_id=agent_id)
        auto_compile = (await load_wiki_source_sync_config(db, agent_id=agent_id)).auto_compile
    if not (config.knowledge_bases or config.include_notes):
        return _NOTHING_TO_DO

    archiver = get_wiki_archiver(llm, agent_id=agent_id)
    # The first backfill is compiled on the user's say-so (cost estimate first); only a settled library auto-compiles changes.
    # Even then a file only queues after the duplicate scan, so copies of one document are not compiled twice.
    deferred = (
        DeferredCompileEnqueue(archiver._compiler, archiver._structure) if auto_compile and state.backfill_complete else None
    )

    scan_completed = False
    try:
        async with ImaTransport(credentials) as transport:
            ctx = SyncContext(
                agent_id=agent_id,
                client=ImaClient(transport),
                structure=archiver._structure,
                config=config,
                state=state,
                ledger=ImaLedger(normalize_agent_scope(agent_id)),
                deadline=time.monotonic() + SLICE_BUDGET_S,
                compiler_enqueue=deferred,
                stop=stop,
            )
            outcome = await run_slice(ctx)
        if (outcome.finished and outcome.generation_total > 0) or (deferred is not None and deferred.needs_scan):
            scan_completed = await run_post_sync_dedup_scan(agent_id=agent_id)
    finally:
        # A failing slice must not strand files it already wrote.
        if deferred is not None:
            await deferred.release(scan_completed=scan_completed)

    if outcome.published > 0:
        from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

        await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
    return _to_job_outcome(outcome)


def _to_job_outcome(outcome: SliceOutcome) -> ImaJobOutcome:
    retry_at = datetime.now(UTC) + timedelta(seconds=outcome.retry_after_s) if outcome.retry_after_s is not None else None
    summary = f"ima: {outcome.generation_total} imported" if outcome.finished and outcome.generation_total else SILENT
    return ImaJobOutcome(summary, skipped=outcome.error_kind != "" and retry_at is None, retry_at=retry_at)
