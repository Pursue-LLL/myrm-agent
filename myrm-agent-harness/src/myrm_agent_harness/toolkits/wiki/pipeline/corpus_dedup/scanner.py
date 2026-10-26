"""Scan wiki raw corpus for duplicate groups.

[POS]
See module docstring.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.fingerprint import (
    build_fingerprint,
    is_near_duplicate,
    recommend_keep_path,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.store import (
    CorpusDedupStore,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
    DedupTier,
    DuplicateMember,
    GroupStatus,
    PlannedGroup,
    RawFileFingerprint,
    ScanProgress,
    ScanResult,
)

# Fingerprints are stored in batches: far fewer transactions than one per file, and an interrupted scan keeps its work.
_FINGERPRINT_BATCH = 200


class CorpusDedupScanner:
    """Scan eligible raw files and persist duplicate groups."""

    def __init__(self, structure: WikiStructure) -> None:
        self._structure = structure
        self._store = CorpusDedupStore(structure)
        from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.eligibility import (
            CorpusEligibilityFilter,
        )

        self._eligibility = CorpusEligibilityFilter(structure)

    @property
    def store(self) -> CorpusDedupStore:
        return self._store

    def scan(self, *, incremental: bool = False) -> ScanResult:
        # Taken before the corpus is listed: every file written earlier is part of what this scan looks at.
        started_ns = time.time_ns()
        start = time.perf_counter()
        raw_files = self._eligibility.filter_raw_paths(self._structure.list_raw_files())
        total = len(raw_files)
        active_paths: set[str] = set()
        fingerprints: list[RawFileFingerprint] = []
        cached = self._store.fingerprints.load_all() if incremental else {}
        unsaved: list[RawFileFingerprint] = []
        files_recomputed = 0

        self._store.set_scan_progress(
            ScanProgress(
                phase="scanning",
                files_scanned=0,
                files_total=total,
                message="Scanning raw corpus",
            )
        )

        for index, raw_file in enumerate(raw_files, start=1):
            try:
                rel = raw_file.relative_to(self._structure.raw_dir).as_posix()
                active_paths.add(rel)
                fingerprint, recomputed = self._resolve_fingerprint(raw_file, rel, cached.get(rel))
                fingerprints.append(fingerprint)
                if recomputed:
                    files_recomputed += 1
                    unsaved.append(fingerprint)
            except OSError:
                continue
            if len(unsaved) >= _FINGERPRINT_BATCH:
                self._store.fingerprints.upsert_many(unsaved)
                unsaved.clear()
            if index % 25 == 0 or index == total:
                self._store.set_scan_progress(
                    ScanProgress(
                        phase="scanning",
                        files_scanned=index,
                        files_total=total,
                        message="Scanning raw corpus",
                    )
                )

        self._store.fingerprints.upsert_many(unsaved)
        removed_cache = self._store.fingerprints.prune(active_paths)
        if incremental and files_recomputed == 0 and removed_cache == 0:
            open_groups = len(self._store.list_groups(status=GroupStatus.OPEN))
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._store.confirm_scan_coverage(started_ns)
            self._store.mark_scan_complete()
            self._store.set_scan_progress(
                ScanProgress(
                    phase="done",
                    files_scanned=total,
                    files_total=total,
                    groups_found=open_groups,
                    message="Scan complete (incremental cache hit)",
                )
            )
            return ScanResult(
                files_scanned=total,
                groups_found=open_groups,
                open_groups=open_groups,
                exact_groups=0,
                normalized_groups=0,
                near_groups=0,
                duration_ms=duration_ms,
                incremental=True,
            )

        self._store.set_scan_progress(
            ScanProgress(
                phase="grouping",
                files_scanned=total,
                files_total=total,
                message="Grouping duplicates",
            )
        )
        planned = self._plan_groups(fingerprints)
        self._store.replace_scan_groups(planned, scan_started_ns=started_ns)
        self._store.mark_scan_complete()
        self._store.set_scan_progress(
            ScanProgress(
                phase="done",
                files_scanned=total,
                files_total=total,
                groups_found=len(planned),
                message="Scan complete",
            )
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        open_groups = len(self._store.list_groups(status=GroupStatus.OPEN))
        return ScanResult(
            files_scanned=total,
            groups_found=len(planned),
            open_groups=open_groups,
            exact_groups=sum(1 for group in planned if group.tier == DedupTier.EXACT),
            normalized_groups=sum(1 for group in planned if group.tier == DedupTier.NORMALIZED),
            near_groups=sum(1 for group in planned if group.tier == DedupTier.NEAR),
            duration_ms=duration_ms,
            incremental=incremental,
        )

    @staticmethod
    def _resolve_fingerprint(
        raw_file: Path,
        relative_path: str,
        cached: RawFileFingerprint | None,
    ) -> tuple[RawFileFingerprint, bool]:
        """The cached fingerprint while the file is unchanged, else a fresh one (and True)."""
        stat = raw_file.stat()
        if cached is not None and cached.size_bytes == stat.st_size and cached.mtime_ns == stat.st_mtime_ns:
            return cached, False
        return build_fingerprint(raw_file, relative_path=relative_path), True

    def _plan_groups(self, fingerprints: list[RawFileFingerprint]) -> list[PlannedGroup]:
        """Work out every duplicate group in memory; each file lands in the strictest tier that matches it."""
        deferred_member_sets = self._store.collect_deferred_member_sets()
        planned: list[PlannedGroup] = []
        grouped_paths: set[str] = set()

        exact = self._group_by_key(
            fingerprints,
            key=lambda item: item.exact_hash,
            tier=DedupTier.EXACT,
            deferred_member_sets=deferred_member_sets,
        )
        planned.extend(exact)
        grouped_paths.update(path for group in exact for path in group.member_paths)

        normalized = self._group_by_key(
            [item for item in fingerprints if item.relative_path not in grouped_paths],
            key=lambda item: item.normalized_hash,
            tier=DedupTier.NORMALIZED,
            deferred_member_sets=deferred_member_sets,
        )
        planned.extend(normalized)
        grouped_paths.update(path for group in normalized for path in group.member_paths)

        planned.extend(
            self._group_near(
                [item for item in fingerprints if item.relative_path not in grouped_paths],
                deferred_member_sets=deferred_member_sets,
            )
        )
        return planned

    def _group_by_key(
        self,
        fingerprints: list[RawFileFingerprint],
        *,
        key: Callable[[RawFileFingerprint], str],
        tier: DedupTier,
        deferred_member_sets: set[frozenset[str]],
    ) -> list[PlannedGroup]:
        buckets: dict[str, list[RawFileFingerprint]] = defaultdict(list)
        for item in fingerprints:
            buckets[key(item)].append(item)
        return [
            self._plan_group(tier, bucket_key, members, deferred_member_sets)
            for bucket_key, members in buckets.items()
            if len(members) >= 2 and not self._should_skip_group(members)
        ]

    def _group_near(
        self,
        fingerprints: list[RawFileFingerprint],
        *,
        deferred_member_sets: set[frozenset[str]],
    ) -> list[PlannedGroup]:
        if len(fingerprints) < 2:
            return []
        assigned: set[str] = set()
        groups: list[PlannedGroup] = []
        ordered = sorted(fingerprints, key=lambda item: item.relative_path)
        for index, anchor in enumerate(ordered):
            if anchor.relative_path in assigned:
                continue
            cluster = [anchor]
            for candidate in ordered[index + 1 :]:
                if candidate.relative_path in assigned:
                    continue
                if is_near_duplicate(anchor.simhash, candidate.simhash):
                    cluster.append(candidate)
            if len(cluster) < 2 or self._should_skip_group(cluster):
                continue
            groups.append(self._plan_group(DedupTier.NEAR, f"near:{anchor.simhash:x}", cluster, deferred_member_sets))
            assigned.update(member.relative_path for member in cluster)
        return groups

    def _plan_group(
        self,
        tier: DedupTier,
        fingerprint: str,
        members: list[RawFileFingerprint],
        deferred_member_sets: set[frozenset[str]],
    ) -> PlannedGroup:
        return PlannedGroup(
            tier=tier,
            fingerprint=fingerprint,
            recommended_keep_path=recommend_keep_path(members),
            members=tuple(
                DuplicateMember(
                    relative_path=member.relative_path,
                    size_bytes=member.size_bytes,
                    mtime_ns=member.mtime_ns,
                )
                for member in members
            ),
            status=self._resolve_group_status(members, deferred_member_sets),
        )

    def _should_skip_group(self, members: list[RawFileFingerprint]) -> bool:
        paths = [member.relative_path for member in members]
        if len(paths) < 2:
            return False
        for left_index, left in enumerate(paths):
            for right in paths[left_index + 1 :]:
                if not self._store.is_pair_dismissed(left, right):
                    return False
        return True

    def _resolve_group_status(
        self,
        members: list[RawFileFingerprint],
        deferred_member_sets: set[frozenset[str]],
    ) -> GroupStatus:
        member_paths = frozenset(member.relative_path for member in members)
        if self._matches_deferred_cluster(member_paths, deferred_member_sets):
            return GroupStatus.DEFERRED
        return GroupStatus.OPEN

    @staticmethod
    def _matches_deferred_cluster(
        member_paths: frozenset[str],
        deferred_member_sets: set[frozenset[str]],
    ) -> bool:
        """Keep deferred status when a rescan regroups or grows the same duplicate cluster."""
        if len(member_paths) < 2:
            return False
        for deferred_paths in deferred_member_sets:
            if len(deferred_paths) < 2:
                continue
            overlap = deferred_paths & member_paths
            if len(overlap) < 2:
                continue
            if deferred_paths <= member_paths or member_paths <= deferred_paths:
                return True
        return False
