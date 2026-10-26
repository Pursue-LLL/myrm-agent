"""Wiki corpus dedup orchestration SSOT for REST and cron.

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup (POS: scan/govern/eligibility engine)
- app.services.wiki.vault::get_wiki_structure (POS: vault layout without an archiver)

[OUTPUT]
- schedule_wiki_dedup_scan: background scan with progress in store
- run_wiki_dedup_scan_job: blocking scan for cron summaries
- run_post_sync_dedup_scan: best-effort incremental scan after new raw files landed; True only when it completed
- apply_wiki_dedup_disposition: user disposition handler
- get_wiki_dedup_vault_hygiene: trashed/excluded listings for Settings
- restore_wiki_dedup_trashed / undo_wiki_dedup_excluded: vault hygiene undo paths
- get_wiki_dedup_group_snippets: body previews for duplicate review UI

[POS]
Server SSOT bridging POST /wiki/dedup/* and router cron __wiki_dedup__ commands. Scans, listings and hygiene work on the
vault files alone, and scans of one vault run one at a time. Only dispositions that re-queue sources (trash, restore)
take the caller's archiver, bound to the user's model, because the compile worker they wake must be able to compile.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.wiki import WikiIngestionQueue, WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
    CorpusDedupGovernor,
    CorpusDedupScanner,
    CorpusDedupStore,
    CorpusEligibilityFilter,
    DedupStats,
    DispositionAction,
    DispositionResult,
    DuplicateGroup,
    DuplicateMemberSnippet,
    ExcludedRawEntry,
    ScanProgress,
    ScanResult,
    TrashedRawEntry,
    VaultHygieneSnapshot,
)

if TYPE_CHECKING:
    from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

_COMPILE_BUSY_REASON = "compile_in_progress"
_SCAN_BUSY_REASON = "scan_in_progress"


@dataclass(frozen=True, slots=True)
class WikiDedupScanScheduleResult:
    accepted: bool
    skipped: bool = False
    skipped_reason: str | None = None


class WikiDedupRunResult:
    __slots__ = ("skipped", "skipped_reason", "scan_result", "summary_text")

    def __init__(
        self,
        *,
        skipped: bool = False,
        skipped_reason: str | None = None,
        scan_result: ScanResult | None = None,
        summary_text: str = "[SILENT]",
    ) -> None:
        self.skipped = skipped
        self.skipped_reason = skipped_reason
        self.scan_result = scan_result
        self.summary_text = summary_text


_scan_lock = asyncio.Lock()
_running_scans: set[str] = set()
_vault_scan_locks: dict[str, threading.Lock] = {}
_vault_scan_locks_guard = threading.Lock()


def _scan_scope_key(agent_id: str | None) -> str:
    return agent_id or "__default__"


def _vault_structure(agent_id: str | None) -> WikiStructure:
    from app.services.wiki.vault import get_wiki_structure

    return get_wiki_structure(agent_id)


def _compile_is_busy(structure: WikiStructure) -> bool:
    return WikiIngestionQueue(structure).get_stats()["processing"] > 0


def _vault_scan_lock(structure: WikiStructure) -> threading.Lock:
    # Keyed by the resolved vault directory: an implicit and a named default agent share one vault.
    with _vault_scan_locks_guard:
        return _vault_scan_locks.setdefault(str(structure.base_dir), threading.Lock())


def _run_scan_sync(*, agent_id: str | None, incremental: bool) -> ScanResult:
    """Scan one vault, waiting for any scan already running on it.

    Overlapping scans would each rebuild the group table from their own snapshot, and whichever finished last would
    keep a view that is older than the other's.
    """
    structure = _vault_structure(agent_id)
    with _vault_scan_lock(structure):
        return CorpusDedupScanner(structure).scan(incremental=incremental)


async def _execute_background_scan(*, agent_id: str | None, incremental: bool) -> None:
    scope_key = _scan_scope_key(agent_id)
    try:
        await asyncio.to_thread(_run_scan_sync, agent_id=agent_id, incremental=incremental)
    except Exception as exc:
        logger.error("Background wiki dedup scan failed for scope %s: %s", scope_key, exc)
        try:
            CorpusDedupStore(_vault_structure(agent_id)).set_scan_progress(
                ScanProgress(phase="failed", message="Dedup scan failed"),
            )
        except Exception as store_exc:
            logger.warning("Failed to persist dedup scan failure progress: %s", store_exc)
    finally:
        async with _scan_lock:
            _running_scans.discard(scope_key)


async def schedule_wiki_dedup_scan(
    *,
    agent_id: str | None = None,
    incremental: bool = True,
) -> WikiDedupScanScheduleResult:
    if _compile_is_busy(_vault_structure(agent_id)):
        return WikiDedupScanScheduleResult(
            accepted=False,
            skipped=True,
            skipped_reason=_COMPILE_BUSY_REASON,
        )

    scope_key = _scan_scope_key(agent_id)
    async with _scan_lock:
        if scope_key in _running_scans:
            return WikiDedupScanScheduleResult(
                accepted=False,
                skipped=True,
                skipped_reason=_SCAN_BUSY_REASON,
            )
        _running_scans.add(scope_key)
        asyncio.create_task(_execute_background_scan(agent_id=agent_id, incremental=incremental))

    return WikiDedupScanScheduleResult(accepted=True)


async def run_wiki_dedup_scan_job(*, agent_id: str | None = None, incremental: bool = True) -> WikiDedupRunResult:
    if _compile_is_busy(_vault_structure(agent_id)):
        return WikiDedupRunResult(
            skipped=True,
            skipped_reason=_COMPILE_BUSY_REASON,
            summary_text="[SILENT]",
        )

    scan_result = await asyncio.to_thread(_run_scan_sync, agent_id=agent_id, incremental=incremental)
    if scan_result.open_groups <= 0:
        summary = "[SILENT]"
    else:
        summary = (
            f"Wiki dedup scan: {scan_result.open_groups} duplicate group(s) pending review "
            f"({scan_result.exact_groups} exact, {scan_result.normalized_groups} normalized, "
            f"{scan_result.near_groups} near)"
        )
    return WikiDedupRunResult(scan_result=scan_result, summary_text=summary)


async def run_post_sync_dedup_scan(*, agent_id: str | None) -> bool:
    """Scan incrementally after new raw files landed; True only when the scan ran to completion.

    It does not wait for a running compile: the files it vets are held back from the queue, so that compile is working
    on other documents, and the scan only reads raw files and writes the dedup store. A failed scan returns False, so a
    caller that gates on the result falls back to its unguarded behaviour instead of trusting stale groups.
    """
    try:
        await asyncio.to_thread(_run_scan_sync, agent_id=agent_id, incremental=True)
    except Exception as exc:
        logger.warning("Post-sync wiki dedup scan failed: %s", exc)
        return False
    return True


async def apply_wiki_dedup_disposition(
    *,
    archiver: MemoryToWikiArchiver,
    group_id: int,
    action: DispositionAction,
    reason: str,
) -> DispositionResult:
    governor = CorpusDedupGovernor(archiver._structure)
    return await governor.apply_disposition(
        group_id,
        action,
        reason=reason,
        compiler=archiver._compiler,
        indexer=archiver._query_engine._indexer,
    )


def get_wiki_dedup_progress(*, agent_id: str | None = None) -> ScanProgress:
    return CorpusDedupStore(_vault_structure(agent_id)).get_scan_progress()


def get_wiki_dedup_stats(*, agent_id: str | None = None) -> DedupStats:
    eligibility = CorpusEligibilityFilter(_vault_structure(agent_id))
    return eligibility.store.build_stats(eligible_raw_count=eligibility.count_eligible_raw_files())


def list_wiki_dedup_groups(*, agent_id: str | None = None) -> list[DuplicateGroup]:
    return CorpusDedupStore(_vault_structure(agent_id)).list_groups()


def get_wiki_dedup_group_snippets(*, agent_id: str | None, group_id: int) -> list[DuplicateMemberSnippet]:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.snippets import (
        build_group_body_snippets,
    )

    structure = _vault_structure(agent_id)
    group = CorpusDedupStore(structure).get_group(group_id)
    if group is None:
        msg = f"Duplicate group not found: {group_id}"
        raise ValueError(msg)
    return build_group_body_snippets(structure, group)


def wiki_dedup_blocks_compile(*, agent_id: str | None = None) -> bool:
    return len(CorpusDedupGovernor(_vault_structure(agent_id)).blocking_open_groups()) > 0


def is_wiki_dedup_scan_running(*, agent_id: str | None = None) -> bool:
    return _scan_scope_key(agent_id) in _running_scans


def wiki_dedup_checklist_ready(*, agent_id: str | None = None) -> bool:
    structure = _vault_structure(agent_id)
    if not structure.list_raw_files():
        return True
    if CorpusDedupStore(structure).get_last_scan_at() is None:
        return False
    return not wiki_dedup_blocks_compile(agent_id=agent_id)


def get_wiki_dedup_vault_hygiene(*, agent_id: str | None = None) -> VaultHygieneSnapshot:
    return CorpusDedupGovernor(_vault_structure(agent_id)).list_vault_hygiene()


async def restore_wiki_dedup_trashed(
    *,
    archiver: MemoryToWikiArchiver,
    agent_id: str | None,
    relative_path: str,
) -> TrashedRawEntry:
    governor = CorpusDedupGovernor(archiver._structure)
    restored = await governor.restore_trashed_raw(
        relative_path,
        compiler=archiver._compiler,
    )
    await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
    return restored


async def undo_wiki_dedup_excluded(
    *,
    agent_id: str | None,
    relative_path: str,
) -> ExcludedRawEntry:
    governor = CorpusDedupGovernor(_vault_structure(agent_id))
    restored = governor.undo_excluded_raw(relative_path)
    await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
    return restored
