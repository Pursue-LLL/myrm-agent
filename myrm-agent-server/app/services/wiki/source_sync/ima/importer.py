"""Import pending ledger rows into wiki raw/ with bounded concurrency, per-item timeouts and honest outcomes.

[INPUT]
- .content (POS: item → Markdown resolution)
- .context::SyncContext / .ledger (POS: slice context, status transitions)
- app.services.wiki.source_sync.publish_helpers::publish_source_markdown (POS: raw gate publish)

[OUTPUT]
- run_import: drain pending rows until none remain, the time budget ends, or a fatal failure stops the pool

[POS]
Every row ends in exactly one recorded outcome: synced, a terminal status (unsupported / too large / blocked /
duplicate), or a failure whose retry budget reflects whether retrying can help. Only credential rejection, rate
limiting and a run of consecutive connection-level failures stop the pool; one bad item, including a dead link,
never aborts the slice.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from enum import StrEnum

from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawGateError

from app.database.connection import get_session
from app.services.wiki.source_sync.publish_helpers import RawConflictPolicy, publish_source_markdown

from .content import ImaContent, ImaDuplicate, ImaUnsupported, render_document, resolve_kb_item, resolve_note
from .context import SyncContext
from .errors import ImaAuthError, ImaError, ImaPageUnavailableError, ImaRateLimitError, ImaTooLargeError, ImaTransientError
from .identity import NOTES_LANE, build_raw_path, note_item_key
from .ledger import LedgerRow, LedgerStatus

logger = logging.getLogger(__name__)

_WORKERS = 3
_CLAIM_BATCH = 12
_ITEM_TIMEOUT_S = 150.0
_PACE_S = 0.3
_TRANSIENT_STREAK_LIMIT = 6
_SUPERSEDE_REASON = "ima item changed"


class _Outcome(StrEnum):
    DONE = "done"
    TRANSIENT = "transient"


def _raw_path_for(row: LedgerRow) -> str:
    if row.raw_path:
        return row.raw_path
    is_note = row.container_id == NOTES_LANE
    folders = [row.folder_path] if is_note and row.folder_path else row.folder_path.split("/") if row.folder_path else []
    return build_raw_path(
        container=NOTES_LANE if is_note else row.container_name,
        folders=folders,
        title=row.title,
        item_key=row.item_key,
    )


def _modified_date(row: LedgerRow) -> str:
    if row.container_id != NOTES_LANE or not row.remote_version.isdigit() or int(row.remote_version) <= 0:
        return ""
    return datetime.fromtimestamp(int(row.remote_version) / 1000, UTC).strftime("%Y-%m-%d")


async def _note_covered(ctx: SyncContext, note_id: str) -> bool:
    async with get_session() as db:
        return await ctx.ledger.has_item(db, note_item_key(note_id))


async def _resolve(ctx: SyncContext, row: LedgerRow, raw_path: str) -> ImaContent | ImaUnsupported | ImaDuplicate:
    if row.container_id == NOTES_LANE:
        return await resolve_note(ctx.client, row.remote_id)
    return await resolve_kb_item(
        ctx.client,
        row,
        structure=ctx.structure,
        raw_relative=raw_path,
        note_covered=lambda note_id: _note_covered(ctx, note_id),
    )


async def _record_terminal(ctx: SyncContext, row: LedgerRow, status: LedgerStatus, reason: str) -> None:
    async with get_session() as db:
        await ctx.ledger.record_terminal(db, row, status, reason=reason)
        await db.commit()


async def _record_failure(ctx: SyncContext, row: LedgerRow, kind: str, *, final: bool) -> None:
    async with get_session() as db:
        await ctx.ledger.record_failure(db, row, kind=kind, final=final)
        await db.commit()


async def _import_row(ctx: SyncContext, row: LedgerRow) -> None:
    raw_path = _raw_path_for(row)
    resolved = await asyncio.wait_for(_resolve(ctx, row, raw_path), timeout=_ITEM_TIMEOUT_S)
    if isinstance(resolved, ImaUnsupported):
        await _record_terminal(ctx, row, LedgerStatus.UNSUPPORTED, resolved.reason)
        return
    if isinstance(resolved, ImaDuplicate):
        await _record_terminal(ctx, row, LedgerStatus.DUPLICATE, "")
        return

    result = await publish_source_markdown(
        ctx.structure,
        relative_path=raw_path,
        content=render_document(row=row, content=resolved, modified=_modified_date(row)),
        auto_compile=ctx.compiler_enqueue is not None,
        compiler_enqueue=ctx.compiler_enqueue,
        conflict_policy=RawConflictPolicy.SUPERSEDE,
        supersede_reason=_SUPERSEDE_REASON,
    )
    if result.security_blocked:
        await _record_terminal(ctx, row, LedgerStatus.BLOCKED, "security")
        return
    lossy = [*resolved.lossy, *(["redacted"] if result.security_redacted else [])]
    async with get_session() as db:
        await ctx.ledger.record_synced(
            db,
            row,
            raw_path=raw_path,
            fidelity="partial" if lossy else "full",
            notes=lossy,
            char_count=len(resolved.body),
        )
        await db.commit()
    if result.written:
        ctx.state.generation_published += 1


async def _import_guarded(ctx: SyncContext, row: LedgerRow) -> _Outcome:
    """Run one row and record its outcome; re-raise only the failures that must stop the whole pool."""
    try:
        await _import_row(ctx, row)
    except ImaAuthError:
        if row.container_id != NOTES_LANE:
            raise
        await _record_failure(ctx, row, "notes_permission", final=True)
    except ImaRateLimitError:
        raise
    except ImaTooLargeError:
        await _record_terminal(ctx, row, LedgerStatus.TOO_LARGE, "too_large")
    except ImaPageUnavailableError as exc:
        # A dead link is that item's own failure (retried on later passes), not a sign that the connection is sick.
        await _record_failure(ctx, row, exc.kind, final=False)
    except ImaTransientError as exc:
        await _record_failure(ctx, row, exc.kind, final=False)
        return _Outcome.TRANSIENT
    except ImaError as exc:
        await _record_failure(ctx, row, exc.kind, final=True)
    except TimeoutError:
        await _record_failure(ctx, row, "timeout", final=False)
        return _Outcome.TRANSIENT
    except RawGateError as exc:
        logger.warning("ima item %s rejected by the raw gate: %s", row.item_key, exc)
        await _record_failure(ctx, row, exc.code, final=True)
    except Exception:
        logger.exception("ima item %s failed unexpectedly", row.item_key)
        await _record_failure(ctx, row, "internal", final=True)
    return _Outcome.DONE


async def run_import(ctx: SyncContext) -> bool:
    """Return True when no importable row remains; raise the failure that stopped the pool otherwise."""
    pending: deque[LedgerRow] = deque()
    attempted: set[str] = set()
    claim_lock = asyncio.Lock()
    fatal: list[Exception] = []
    drained = False
    transient_streak = 0

    async def next_row() -> LedgerRow | None:
        nonlocal drained
        async with claim_lock:
            if not pending:
                async with get_session() as db:
                    rows = await ctx.ledger.claim(db, limit=_CLAIM_BATCH, containers=ctx.config.containers, exclude=attempted)
                pending.extend(rows)
                attempted.update(row.item_key for row in rows)
                drained = not rows
            return pending.popleft() if pending else None

    async def worker() -> None:
        nonlocal transient_streak
        while not fatal and ctx.time_left() > 0:
            try:
                row = await next_row()
            except Exception as exc:
                # The ledger itself failed: stop every worker and let the slice report it, rather than leave siblings running.
                fatal.append(exc)
                return
            if row is None:
                return
            try:
                outcome = await _import_guarded(ctx, row)
            except (ImaAuthError, ImaRateLimitError) as exc:
                fatal.append(exc)
                return
            transient_streak = transient_streak + 1 if outcome is _Outcome.TRANSIENT else 0
            if transient_streak >= _TRANSIENT_STREAK_LIMIT:
                fatal.append(ImaTransientError("repeated transient failures while importing"))
                return
            await asyncio.sleep(_PACE_S)

    await asyncio.gather(*(worker() for _ in range(_WORKERS)))
    if fatal:
        raise fatal[0]
    return drained
