"""Pre-boot promotion: swap staged state into place before any database opens.

[INPUT]
- app.services.instance_archive.models (POS: pending marker, outcome, layout)
- myrm_agent_harness.infra.state_archive (POS: journaled promotion + crash recovery)
- psutil: requester liveness (pid + start time, immune to pid reuse)

[OUTPUT]
- run_pending_promotion: recover an interrupted swap, then promote a pending marker
- read_outcome / acknowledge_outcome: one-time result for the UI
- prepare_pending_for / prepare_rollback: queue a swap (or the swap back to the pre-swap state)

[POS]
Called from the server lifespan after the persistent root is configured and
before ``init_database``. It must never block or break boot: every failure
turns into a recorded outcome and the previous state stays (or is restored).
The aside directory of the latest swap is kept so the user can undo it once.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil
from myrm_agent_harness.infra.state_archive import (
    PromotionJournal,
    PromotionPhase,
    PromotionPlan,
    promote,
    recover_interrupted,
)

from app.services.instance_archive.models import (
    ArchivePaths,
    Operation,
    OutcomeStatus,
    PendingPromotion,
    PromotionOutcome,
    read_json,
    write_json_atomic,
)

logger = logging.getLogger(__name__)

_ENTRIES_FILE = ".entries.json"
_POLL_SECONDS = 0.25


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _requester_alive(pending: PendingPromotion) -> bool:
    try:
        process = psutil.Process(pending.requester_pid)
        same_process = abs(process.create_time() - pending.requester_started_at) < 1.0
        return bool(same_process and process.is_running() and process.status() != psutil.STATUS_ZOMBIE)
    except psutil.Error:
        return False


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def _record(paths: ArchivePaths, outcome: PromotionOutcome) -> PromotionOutcome:
    outcome.save(paths.result)
    return outcome


def _failure(paths: ArchivePaths, pending: PendingPromotion, code: str) -> PromotionOutcome:
    return _record(
        paths, PromotionOutcome(operation=pending.operation, status=OutcomeStatus.FAILED, completed_at=_now(), error_code=code)
    )


def _prune_asides(paths: ArchivePaths, keep: Path | None) -> None:
    if not paths.aside.is_dir():
        return
    for child in paths.aside.iterdir():
        if keep is None or child.resolve() != keep.resolve():
            shutil.rmtree(child, ignore_errors=True)


def _finish_committed(paths: ArchivePaths, pending: PendingPromotion) -> PromotionOutcome:
    staging, aside = Path(pending.staging_dir), Path(pending.aside_dir)
    undoable = pending.operation is not Operation.ROLLBACK
    if undoable:
        aside.mkdir(parents=True, exist_ok=True)
        write_json_atomic(aside / _ENTRIES_FILE, {"entries": list(pending.entries)})
    shutil.rmtree(staging, ignore_errors=True)
    _prune_asides(paths, keep=aside if undoable else None)
    return _record(
        paths,
        PromotionOutcome(
            operation=pending.operation,
            status=OutcomeStatus.RESTORED,
            completed_at=_now(),
            summary=pending.summary,
            reentry=pending.reentry,
            rollback_available=undoable,
        ),
    )


def run_pending_promotion(state_dir: Path, *, wait_seconds: float = 15.0) -> PromotionOutcome | None:
    """Returns the recorded outcome, or None when there was nothing to do."""
    paths = ArchivePaths(state_dir)
    recovered = recover_interrupted(paths.journal)
    pending = PendingPromotion.load(paths.pending)
    if pending is None:
        if recovered is not None:
            logger.warning("[InstanceArchive] Rolled back an interrupted swap with no pending marker")
        return None

    journal = PromotionJournal.load(paths.journal)
    if journal is not None and journal.staging_root == pending.staging_dir:
        paths.pending.unlink(missing_ok=True)
        if journal.phase is PromotionPhase.COMMITTED:
            return _finish_committed(paths, pending)
        shutil.rmtree(pending.staging_dir, ignore_errors=True)
        return _failure(paths, pending, "interrupted")

    if not (_inside(Path(pending.staging_dir), paths.root) and _inside(Path(pending.aside_dir), paths.root)):
        paths.pending.unlink(missing_ok=True)
        logger.error("[InstanceArchive] Pending marker points outside the working directory; ignored")
        return _failure(paths, pending, "invalid_marker")
    if not Path(pending.staging_dir).is_dir():
        paths.pending.unlink(missing_ok=True)
        return _failure(paths, pending, "staging_missing")

    deadline = time.monotonic() + wait_seconds
    while _requester_alive(pending):
        if time.monotonic() >= deadline:
            logger.warning("[InstanceArchive] Requester process is still running; promotion deferred")
            return _record(
                paths, PromotionOutcome(operation=pending.operation, status=OutcomeStatus.WAITING, completed_at=_now())
            )
        time.sleep(_POLL_SECONDS)

    plan = PromotionPlan(
        live_root=state_dir,
        staging_root=Path(pending.staging_dir),
        aside_root=Path(pending.aside_dir),
        journal_path=paths.journal,
        entries=pending.entries,
    )
    result = promote(plan)
    if result.phase is PromotionPhase.COMMITTED:
        paths.pending.unlink(missing_ok=True)
        return _finish_committed(paths, pending)
    if result.phase is PromotionPhase.ROLLED_BACK:
        paths.pending.unlink(missing_ok=True)
        shutil.rmtree(pending.staging_dir, ignore_errors=True)
        return _failure(paths, pending, "promotion_failed")
    # Rollback itself could not finish: keep the marker/journal so the next boot retries recovery.
    return _failure(paths, pending, "rollback_incomplete")


def read_outcome(state_dir: Path) -> PromotionOutcome | None:
    return PromotionOutcome.load(ArchivePaths(state_dir).result)


def acknowledge_outcome(state_dir: Path) -> None:
    paths = ArchivePaths(state_dir)
    outcome = PromotionOutcome.load(paths.result)
    if outcome is not None and outcome.status is not OutcomeStatus.WAITING:
        paths.result.unlink(missing_ok=True)


def latest_aside(state_dir: Path) -> tuple[Path, tuple[str, ...]] | None:
    """The aside directory of the latest committed swap and the entries it covers."""
    paths = ArchivePaths(state_dir)
    if not paths.aside.is_dir():
        return None
    for child in sorted(paths.aside.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        raw = read_json(child / _ENTRIES_FILE)
        entries = raw.get("entries") if raw else None
        if isinstance(entries, list):
            return child, tuple(str(e) for e in entries)
    return None


def prepare_pending_for(
    paths: ArchivePaths,
    *,
    operation: Operation,
    staging: Path,
    aside: Path,
    entries: tuple[str, ...],
    summary: dict[str, int] | None = None,
    reentry: tuple[str, ...] = (),
) -> PendingPromotion:
    """Write the marker the next boot promotes; the calling process is recorded as the requester."""
    pending = PendingPromotion(
        operation=operation,
        staging_dir=str(staging),
        aside_dir=str(aside),
        entries=entries,
        requester_pid=os.getpid(),
        requester_started_at=psutil.Process().create_time(),
        created_at=_now(),
        summary=summary or {},
        reentry=reentry,
    )
    pending.save(paths.pending)
    return pending


def prepare_rollback(state_dir: Path) -> PendingPromotion | None:
    """Queue a swap that puts the pre-swap state back; None when nothing can be undone."""
    paths = ArchivePaths(state_dir)
    found = latest_aside(state_dir)
    if found is None or paths.pending.exists():
        return None
    aside, entries = found
    return prepare_pending_for(
        paths,
        operation=Operation.ROLLBACK,
        staging=aside,
        aside=paths.aside / f"undo-{int(time.time())}",
        entries=entries,
    )


__all__ = [
    "acknowledge_outcome",
    "latest_aside",
    "prepare_pending_for",
    "prepare_rollback",
    "read_outcome",
    "run_pending_promotion",
]
