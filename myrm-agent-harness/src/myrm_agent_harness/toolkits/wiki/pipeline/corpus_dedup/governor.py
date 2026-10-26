"""Apply user dispositions to duplicate groups and release the files held back for them.

[INPUT]
- corpus_dedup.store::CorpusDedupStore (POS: groups, dispositions, compile holds, scan coverage)
- corpus_dedup.eligibility::CorpusEligibilityFilter (POS: blocked-path filter)
- corpus_dedup.types::FileEnqueuer (POS: what a release hands files to)
- core.structure::WikiStructure (POS: vault paths and raw listing)
- pipeline.raw_gate.evidence_removal, pipeline.cognitive_map (POS: evidence re-anchor and audit log)

[OUTPUT]
- CorpusDedupGovernor: ``apply_disposition`` (trash / exclude / dismiss / defer), ``restore_trashed_raw``,
  ``undo_excluded_raw``, ``list_vault_hygiene``, ``blocking_open_groups``, and the compile hold:
  ``hold_for_compile`` / ``has_unscanned_holds`` / ``release_held`` / ``release_unguarded``

[POS]
Policy layer over the dedup store. A disposition settles a group, and the release that follows queues the held files
it cleared, so the survivor of a resolved group compiles without another click. A hold leaves the ledger only after its
enqueue succeeded, and the compile pipeline's own change detection absorbs a repeated release.
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.wiki.core.claims_contract import sha256_raw_file
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map.events import (
    WikiMapEvent,
    WikiMapEventType,
)
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map.writer import (
    append_log_entry,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.eligibility import (
    CorpusEligibilityFilter,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.path_utils import (
    normalize_raw_relative_path,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.store import (
    CorpusDedupStore,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
    DedupTier,
    DispositionAction,
    DispositionResult,
    DuplicateGroup,
    ExcludedRawEntry,
    FileEnqueuer,
    GroupStatus,
    HeldFile,
    TrashedRawEntry,
    VaultHygieneSnapshot,
)
from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate.evidence_removal import (
    remove_raw_evidence,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.pipeline.compiler import WikiCompiler
    from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

logger = logging.getLogger(__name__)


class CorpusDedupGovernor:
    """Execute trash/exclude/dismiss/defer actions for duplicate groups and release the files held for them."""

    def __init__(self, structure: WikiStructure) -> None:
        self._structure = structure
        self._store = CorpusDedupStore(structure)

    @property
    def store(self) -> CorpusDedupStore:
        return self._store

    def get_corpus_trash_dir(self) -> Path:
        trash_dir = self._structure.base_dir / ".corpus_trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        return trash_dir

    async def apply_disposition(
        self,
        group_id: int,
        action: DispositionAction,
        *,
        reason: str,
        compiler: WikiCompiler | None = None,
        indexer: WikiIndexer | None = None,
    ) -> DispositionResult:
        """Apply the action; with a ``compiler``, held files the decision just cleared are queued for compiling."""
        result = await self._dispose(group_id, action, reason=reason, compiler=compiler, indexer=indexer)
        if compiler is not None:
            try:
                await self.release_held(compiler)
            except Exception as exc:
                # The decision is already stored; the held files stay held and go out with the next release.
                logger.warning("Held files could not be released after the disposition: %s", exc)
        return result

    async def _dispose(
        self,
        group_id: int,
        action: DispositionAction,
        *,
        reason: str,
        compiler: WikiCompiler | None,
        indexer: WikiIndexer | None,
    ) -> DispositionResult:
        group = self._store.get_group(group_id)
        if group is None:
            msg = f"Duplicate group not found: {group_id}"
            raise ValueError(msg)

        if action == DispositionAction.DEFER:
            self._store.update_group_status(group_id, GroupStatus.DEFERRED)
            return DispositionResult(group_id=group_id, action=action)

        if action == DispositionAction.DISMISS:
            paths = [member.relative_path for member in group.members]
            for left_index, left in enumerate(paths):
                for right in paths[left_index + 1 :]:
                    self._store.dispositions.add_dismissed_pair(left, right)
            self._store.update_group_status(group_id, GroupStatus.RESOLVED)
            return DispositionResult(group_id=group_id, action=action, affected_paths=tuple(paths))

        affected: list[str] = []
        prevented = 0
        keep_path = group.recommended_keep_path
        for member in group.members:
            if member.relative_path == keep_path:
                continue
            if action == DispositionAction.EXCLUDE:
                self._store.dispositions.add_excluded_path(
                    normalize_raw_relative_path(member.relative_path),
                    reason=reason,
                )
                affected.append(member.relative_path)
                prevented += 1
            elif action == DispositionAction.TRASH:
                moved = await self._trash_raw_path(
                    member.relative_path,
                    reason=reason,
                    compiler=compiler,
                    indexer=indexer,
                )
                if moved:
                    affected.append(member.relative_path)
                    prevented += 1

        if prevented:
            self._store.increment_compile_jobs_prevented(prevented)
        self._store.update_group_status(group_id, GroupStatus.RESOLVED)
        return DispositionResult(
            group_id=group_id,
            action=action,
            affected_paths=tuple(affected),
            compile_jobs_prevented=prevented,
        )

    async def _trash_raw_path(
        self,
        relative_path: str,
        *,
        reason: str,
        compiler: WikiCompiler | None,
        indexer: WikiIndexer | None,
    ) -> bool:
        normalized = normalize_raw_relative_path(relative_path)
        raw_path = self._structure.get_raw_file_path(normalized)
        if not raw_path.exists():
            return False
        content_hash = sha256_raw_file(raw_path)
        trash_dir = self.get_corpus_trash_dir()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        safe_name = relative_path.replace("/", "__")
        trash_name = f"{timestamp}__{safe_name}"
        trash_path = trash_dir / trash_name
        trash_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(raw_path), str(trash_path))
        self._store.dispositions.add_trashed_path(
            normalized,
            trash_relpath=f".corpus_trash/{trash_name}",
            content_hash=content_hash,
        )
        await remove_raw_evidence(
            self._structure,
            normalized,
            reason=reason,
            caller="settings",
            delete_file=False,
            compiler=compiler,
            indexer=indexer,
        )
        return True

    def list_vault_hygiene(self) -> VaultHygieneSnapshot:
        return self._store.dispositions.build_vault_hygiene_snapshot()

    async def restore_trashed_raw(
        self,
        relative_path: str,
        *,
        compiler: FileEnqueuer | None = None,
    ) -> TrashedRawEntry:
        normalized = normalize_raw_relative_path(relative_path)
        entry = self._store.dispositions.get_trashed_entry(normalized)
        if entry is None:
            msg = f"Trashed raw file not found: {normalized}"
            raise ValueError(msg)

        trash_path = self._structure.base_dir / entry.trash_relpath
        if not trash_path.is_file():
            msg = f"Corpus trash file missing on disk: {entry.trash_relpath}"
            raise ValueError(msg)

        raw_path = self._structure.get_raw_file_path(normalized)
        if raw_path.exists():
            msg = f"Raw file already exists: {normalized}"
            raise ValueError(msg)

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(trash_path), str(raw_path))
        if not self._store.dispositions.remove_trashed_path(normalized):
            logger.warning(
                "Restored raw file on disk but failed to clear trashed_paths entry: %s",
                normalized,
            )
        if compiler is not None:
            compiler.enqueue_file(raw_path)
        try:
            append_log_entry(
                self._structure,
                WikiMapEvent(
                    event_type=WikiMapEventType.EVIDENCE_RESTORED,
                    summary=f"Restored raw evidence {normalized}",
                    details={
                        "path": normalized,
                        "trash_relpath": entry.trash_relpath,
                        "content_hash": entry.content_hash,
                    },
                ),
            )
        except OSError as exc:
            logger.warning("Failed to append restore log entry for %s: %s", normalized, exc)
        return entry

    def undo_excluded_raw(self, relative_path: str) -> ExcludedRawEntry:
        normalized = normalize_raw_relative_path(relative_path)
        match = self._store.dispositions.get_excluded_entry(normalized)
        if match is None:
            msg = f"Excluded raw file not found: {normalized}"
            raise ValueError(msg)
        if not self._store.dispositions.remove_excluded_path(normalized):
            msg = f"Excluded raw file not found: {normalized}"
            raise ValueError(msg)
        return match

    def blocking_open_groups(self) -> list[DuplicateGroup]:
        groups = self._store.list_groups(status=GroupStatus.OPEN)
        return [group for group in groups if group.tier in {DedupTier.EXACT, DedupTier.NORMALIZED}]

    def hold_for_compile(self, relative_paths: Iterable[str]) -> None:
        """Keep just-published raw files out of the compile queue until a scan has looked at them.

        Call it after the files are written: a scan only vouches for files that existed when it started.
        """
        self._store.holds.hold(relative_paths, held_at_ns=time.time_ns())

    def has_unscanned_holds(self) -> bool:
        """True when a held file was written after the last scan began, so a scan is still owed."""
        return self._store.holds.any_held_after(self._store.get_scan_coverage_ns())

    async def release_held(self, enqueuer: FileEnqueuer) -> int:
        """Queue the held files that a finished scan has cleared and return how many were queued.

        A file stays held while no scan that began after it was written has finished, and while it belongs to an open
        exact or normalized group: the user decides there, and the survivor is released by that decision.
        """
        coverage_ns = self._store.get_scan_coverage_ns()
        in_open_group = {member.relative_path for group in self.blocking_open_groups() for member in group.members}
        cleared = [
            held
            for held in self._store.holds.list_held()
            if held.held_at_ns <= coverage_ns and held.relative_path not in in_open_group
        ]
        return await self._enqueue_held(enqueuer, cleared)

    async def release_unguarded(self, enqueuer: FileEnqueuer, relative_paths: Iterable[str]) -> int:
        """Queue these held files without a scan to vouch for them, so a failed scan never strands a document."""
        wanted = {normalize_raw_relative_path(path) for path in relative_paths}
        return await self._enqueue_held(
            enqueuer, [held for held in self._store.holds.list_held() if held.relative_path in wanted]
        )

    async def _enqueue_held(self, enqueuer: FileEnqueuer, held: list[HeldFile]) -> int:
        """Queue what still needs compiling among ``held`` and clear the holds that are settled.

        Excluded, trashed and vanished files are settled without queueing; so are files whose content was compiled
        already or is being compiled now, which makes a release safe to repeat. A hold whose enqueue failed is kept.
        """
        if not held:
            return 0
        from myrm_agent_harness.toolkits.wiki.pipeline.compiler_enqueue import filter_changed_files
        from myrm_agent_harness.toolkits.wiki.pipeline.queue import WikiIngestionQueue

        blocked = CorpusEligibilityFilter(self._structure).blocked_paths()
        candidates: list[tuple[HeldFile, Path]] = []
        for item in held:
            if item.relative_path in blocked:
                continue
            try:
                raw_path = self._structure.get_raw_file_path(item.relative_path)
            except ValueError:
                continue
            if raw_path.is_file():
                candidates.append((item, raw_path))

        needs_compile = {str(path) for path in await filter_changed_files(self._structure, [p for _, p in candidates])}
        in_flight = set(WikiIngestionQueue(self._structure).list_processing_file_paths())
        queued = 0
        enqueue_failed: set[str] = set()
        for item, raw_path in candidates:
            if str(raw_path) not in needs_compile or str(raw_path) in in_flight:
                continue
            try:
                enqueuer.enqueue_file(raw_path)
            except Exception as exc:
                logger.warning("Held file could not be queued, keeping it held: %s: %s", item.relative_path, exc)
                enqueue_failed.add(item.relative_path)
            else:
                queued += 1
        self._store.holds.drop(item for item in held if item.relative_path not in enqueue_failed)
        return queued
