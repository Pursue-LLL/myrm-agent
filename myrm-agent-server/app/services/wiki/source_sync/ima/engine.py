"""One time-boxed slice of the ima sync: inventory, then import, with failures mapped to scheduling advice.

[INPUT]
- .inventory / .importer (POS: the two phases)
- .context::SyncContext (POS: slice context)

[OUTPUT]
- SliceOutcome: whether the generation finished and when the scheduler should call again
- run_slice

[POS]
The cron lane calls ``run_slice`` repeatedly; each call resumes from the persisted phase, so a restart, a
rate-limit pause or a slice that ran out of time costs nothing. The engine never decides to pause the job:
it only reports ``retry_after_s`` and leaves scheduling to the cron layer. A failure nobody anticipated (ledger,
state or inventory code) is reported as ``internal`` with a backoff, so the card says something went wrong and the
lane keeps retrying instead of leaving the user on "importing" forever.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from .context import SyncContext
from .errors import ImaAuthError, ImaError, ImaRateLimitError
from .importer import run_import
from .inventory import begin_generation, run_inventory

logger = logging.getLogger(__name__)

SLICE_BUDGET_S = 300.0
_SLICE_GAP_S = 5.0
_MIN_RATE_LIMIT_PAUSE_S = 30.0
_BACKOFF_BASE_S = 120.0
_BACKOFF_CAP_S = 3600.0
# Pauses that a later clean slice resolves; per-library failures recorded during inventory stay until the next pass.
_RECOVERABLE_KINDS = frozenset({"auth", "rate_limit", "transient", "page_unavailable", "internal"})


@dataclass(frozen=True, slots=True)
class SliceOutcome:
    """``published`` counts this slice only; ``generation_total`` the whole pass so far."""

    finished: bool
    retry_after_s: float | None
    published: int
    generation_total: int
    error_kind: str = ""


def _backoff_s(streak: int) -> float:
    return min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * float(2 ** min(streak, 5)))


def _note_clean_progress(ctx: SyncContext) -> None:
    ctx.state.failure_streak = 0
    ctx.state.needs_reauth = False
    if ctx.state.last_error_kind in _RECOVERABLE_KINDS:
        ctx.state.last_error_kind = ""


async def run_slice(ctx: SyncContext) -> SliceOutcome:
    state = ctx.state
    published_before = 0

    def outcome(*, finished: bool = False, retry_after_s: float | None, error_kind: str = "") -> SliceOutcome:
        return SliceOutcome(
            finished=finished,
            retry_after_s=retry_after_s,
            published=max(state.generation_published - published_before, 0),
            generation_total=state.generation_published,
            error_kind=error_kind,
        )

    try:
        fingerprint = ctx.config.fingerprint()
        if state.config_fingerprint != fingerprint:
            # The user changed what to import: restart the inventory, and hold back auto-compile until the new scope settles.
            state.config_fingerprint = fingerprint
            state.phase = "idle"
            state.backfill_complete = False
        if state.phase == "idle":
            await begin_generation(ctx)
        published_before = state.generation_published
        if state.phase == "inventory":
            await run_inventory(ctx)
        if state.phase == "fetch" and await run_import(ctx):
            state.phase = "idle"
            state.backfill_complete = True
            state.last_run_at = datetime.now(UTC)
            _note_clean_progress(ctx)
            await ctx.persist_state(force=True)
            return outcome(finished=True, retry_after_s=None)
        _note_clean_progress(ctx)
        await ctx.persist_state(force=True)
        return outcome(retry_after_s=_SLICE_GAP_S)
    except ImaAuthError:
        state.needs_reauth = True
        state.last_error_kind = "auth"
        await ctx.persist_state(force=True)
        return outcome(retry_after_s=None, error_kind="auth")
    except ImaRateLimitError as exc:
        state.last_error_kind = exc.kind
        await ctx.persist_state(force=True)
        return outcome(retry_after_s=max(exc.retry_after_s or 0.0, _MIN_RATE_LIMIT_PAUSE_S), error_kind=exc.kind)
    except ImaError as exc:
        state.failure_streak += 1
        state.last_error_kind = exc.kind
        logger.warning("ima sync slice failed (%s, streak %d): %s", exc.kind, state.failure_streak, exc)
        await ctx.persist_state(force=True)
        return outcome(retry_after_s=_backoff_s(state.failure_streak), error_kind=exc.kind)
    except Exception:
        # Cancellation is a BaseException and still propagates; details stay in the log, never in the job history.
        state.failure_streak += 1
        state.last_error_kind = "internal"
        logger.exception("ima sync slice failed unexpectedly (streak %d)", state.failure_streak)
        await ctx.persist_state(force=True)
        return outcome(retry_after_s=_backoff_s(state.failure_streak), error_kind="internal")
