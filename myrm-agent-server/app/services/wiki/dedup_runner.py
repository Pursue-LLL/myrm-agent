"""Wiki corpus dedup orchestration SSOT for REST and cron.

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup (POS: scan/govern/eligibility engine)

[OUTPUT]
- schedule_wiki_dedup_scan: background scan with progress in store
- run_wiki_dedup_scan_job: blocking scan for cron summaries
- apply_wiki_dedup_disposition: user disposition handler
- get_wiki_dedup_vault_hygiene: trashed/excluded listings for Settings
- restore_wiki_dedup_trashed / undo_wiki_dedup_excluded: vault hygiene undo paths
- get_wiki_dedup_group_snippets: body previews for duplicate review UI

[POS]
Server SSOT bridging POST /wiki/dedup/* and router cron __wiki_dedup__ commands.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
    CorpusDedupGovernor,
    CorpusDedupScanner,
    CorpusEligibilityFilter,
    DispositionAction,
    DispositionResult,
    ExcludedRawEntry,
    ScanProgress,
    ScanResult,
    TrashedRawEntry,
    VaultHygieneSnapshot,
)

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


def _scan_scope_key(agent_id: str | None) -> str:
    return agent_id or "__default__"


def _compile_is_busy(archiver: object) -> bool:
    queue_stats = archiver._queue.get_stats()
    processing = queue_stats.get("processing", 0)
    return isinstance(processing, int) and processing > 0


def _run_scan_sync(*, agent_id: str | None, incremental: bool) -> ScanResult:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    scanner = CorpusDedupScanner(archiver._structure)
    return scanner.scan(incremental=incremental)


async def _execute_background_scan(*, agent_id: str | None, incremental: bool) -> None:
    scope_key = _scan_scope_key(agent_id)
    try:
        await asyncio.to_thread(
            _run_scan_sync, agent_id=agent_id, incremental=incremental
        )
    except Exception as exc:
        logger.error(
            "Background wiki dedup scan failed for scope %s: %s", scope_key, exc
        )
        try:
            from app.services.wiki.vault_service import get_wiki_archiver

            archiver = get_wiki_archiver(None, agent_id=agent_id)
            CorpusDedupScanner(archiver._structure).store.set_scan_progress(
                ScanProgress(phase="failed", message="Dedup scan failed"),
            )
        except Exception as store_exc:
            logger.warning(
                "Failed to persist dedup scan failure progress: %s", store_exc
            )
    finally:
        async with _scan_lock:
            _running_scans.discard(scope_key)


async def schedule_wiki_dedup_scan(
    *,
    agent_id: str | None = None,
    incremental: bool = True,
) -> WikiDedupScanScheduleResult:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    if _compile_is_busy(archiver):
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
        asyncio.create_task(
            _execute_background_scan(agent_id=agent_id, incremental=incremental)
        )

    return WikiDedupScanScheduleResult(accepted=True)


async def run_wiki_dedup_scan_job(
    *, agent_id: str | None = None, incremental: bool = True
) -> WikiDedupRunResult:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    if _compile_is_busy(archiver):
        return WikiDedupRunResult(
            skipped=True,
            skipped_reason=_COMPILE_BUSY_REASON,
            summary_text="[SILENT]",
        )

    scan_result = await asyncio.to_thread(
        _run_scan_sync, agent_id=agent_id, incremental=incremental
    )
    if scan_result.open_groups <= 0:
        summary = "[SILENT]"
    else:
        summary = (
            f"Wiki dedup scan: {scan_result.open_groups} duplicate group(s) pending review "
            f"({scan_result.exact_groups} exact, {scan_result.normalized_groups} normalized, "
            f"{scan_result.near_groups} near)"
        )
    return WikiDedupRunResult(scan_result=scan_result, summary_text=summary)


async def apply_wiki_dedup_disposition(
    *,
    agent_id: str | None,
    group_id: int,
    action: DispositionAction,
    reason: str,
) -> DispositionResult:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    governor = CorpusDedupGovernor(archiver._structure)
    return await governor.apply_disposition(
        group_id,
        action,
        reason=reason,
        compiler=archiver._compiler,
        indexer=archiver._query_engine._indexer,
    )


def get_wiki_dedup_progress(*, agent_id: str | None = None) -> ScanProgress:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    scanner = CorpusDedupScanner(archiver._structure)
    return scanner.store.get_scan_progress()


def get_wiki_dedup_stats(*, agent_id: str | None = None):
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    eligibility = CorpusEligibilityFilter(archiver._structure)
    return eligibility.store.build_stats(
        eligible_raw_count=eligibility.count_eligible_raw_files()
    )


def list_wiki_dedup_groups(*, agent_id: str | None = None):
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    scanner = CorpusDedupScanner(archiver._structure)
    return scanner.store.list_groups()


def get_wiki_dedup_group_snippets(*, agent_id: str | None, group_id: int):
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.snippets import (
        build_group_body_snippets,
    )

    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    store = CorpusDedupScanner(archiver._structure).store
    group = store.get_group(group_id)
    if group is None:
        msg = f"Duplicate group not found: {group_id}"
        raise ValueError(msg)
    return build_group_body_snippets(archiver._structure, group)


def wiki_dedup_blocks_compile(*, agent_id: str | None = None) -> bool:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    governor = CorpusDedupGovernor(archiver._structure)
    return len(governor.blocking_open_groups()) > 0


def is_wiki_dedup_scan_running(*, agent_id: str | None = None) -> bool:
    return _scan_scope_key(agent_id) in _running_scans


def wiki_dedup_checklist_ready(*, agent_id: str | None = None) -> bool:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    store = CorpusDedupScanner(archiver._structure).store
    raw_files = archiver._structure.list_raw_files()
    if not raw_files:
        return True
    if store.get_last_scan_at() is None:
        return False
    return not wiki_dedup_blocks_compile(agent_id=agent_id)


def get_wiki_dedup_vault_hygiene(
    *, agent_id: str | None = None
) -> VaultHygieneSnapshot:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    governor = CorpusDedupGovernor(archiver._structure)
    return governor.list_vault_hygiene()


async def restore_wiki_dedup_trashed(
    *,
    agent_id: str | None,
    relative_path: str,
) -> TrashedRawEntry:
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
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
    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    governor = CorpusDedupGovernor(archiver._structure)
    restored = governor.undo_excluded_raw(relative_path)
    await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
    return restored
