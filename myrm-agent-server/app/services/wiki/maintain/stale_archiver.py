"""Shared Workspace Stale File Archiver Service.

[INPUT]
- myrm_agent_harness.toolkits.wiki.core.fact_trust_contract::FactStatus, resolve_fact_status (POS: SSOT)
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure (POS: vault path manager)

[OUTPUT]
- StaleFileCandidate, StaleArchiveResult, StaleFileArchiver

[POS]
Server-side business service to scan, detect, and archive stale draft and deprecated documents
in shared workspace / LLM-Wiki structures.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.fact_trust_contract import (
    FactStatus,
    resolve_fact_status,
)
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StaleFileCandidate:
    """Candidate file eligible for archival."""

    file_path: str
    fact_status: FactStatus
    last_modified: datetime
    stale_reason: str
    recommended_action: str


@dataclass(frozen=True, slots=True)
class StaleArchiveResult:
    """Result of stale file scanning or archiving execution."""

    scanned_count: int
    stale_candidates: tuple[StaleFileCandidate, ...]
    archived_count: int = 0
    errors: tuple[str, ...] = ()


class StaleFileArchiver:
    """Detects and moves stale drafts / deprecated files into archive/ directory."""

    def __init__(self, structure: WikiStructure) -> None:
        self._structure = structure

    def scan_stale_files(self, *, draft_max_age_days: int = 30) -> StaleArchiveResult:
        """Scan workspace concepts and documents for stale drafts or deprecated materials."""
        candidates: list[StaleFileCandidate] = []
        scanned = 0
        cutoff = datetime.now(UTC) - timedelta(days=draft_max_age_days)

        concepts_dir = self._structure.concepts_dir
        if not concepts_dir.exists():
            return StaleArchiveResult(scanned_count=0, stale_candidates=())

        for file_path in concepts_dir.rglob("*.md"):
            if file_path.name.startswith("."):
                continue
            scanned += 1
            try:
                content = file_path.read_text(encoding="utf-8")
                status = resolve_fact_status(content, file_path=file_path)
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)

                if status == FactStatus.DEPRECATED:
                    candidates.append(
                        StaleFileCandidate(
                            file_path=str(file_path.relative_to(self._structure.base_dir)),
                            fact_status=status,
                            last_modified=mtime,
                            stale_reason="Explicitly marked as deprecated or blocked.",
                            recommended_action="archive",
                        )
                    )
                elif status == FactStatus.IN_PROGRESS_DRAFT and mtime < cutoff:
                    candidates.append(
                        StaleFileCandidate(
                            file_path=str(file_path.relative_to(self._structure.base_dir)),
                            fact_status=status,
                            last_modified=mtime,
                            stale_reason=f"Draft unmodified for >{draft_max_age_days} days.",
                            recommended_action="archive",
                        )
                    )
            except OSError as e:
                logger.warning(f"Failed to scan file {file_path} for stale status: {e}")

        return StaleArchiveResult(
            scanned_count=scanned,
            stale_candidates=tuple(candidates),
        )

    def archive_candidates(self, relative_paths: list[str]) -> StaleArchiveResult:
        """Move selected files into the archive/ partition of the workspace."""
        archive_dir = self._structure.base_dir / "wiki" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        archived = 0
        errors: list[str] = []

        for rel in relative_paths:
            candidate_path = Path(rel)
            src = candidate_path if candidate_path.is_absolute() else (self._structure.base_dir / rel)
            if not src.exists():
                errors.append(f"Source file not found: {rel}")
                continue

            target = archive_dir / src.name
            try:
                shutil.move(str(src), str(target))
                archived += 1
                logger.info(f"Archived stale file: {rel} -> {target}")
            except OSError as e:
                errors.append(f"Failed to archive {rel}: {e}")

        return StaleArchiveResult(
            scanned_count=len(relative_paths),
            stale_candidates=(),
            archived_count=archived,
            errors=tuple(errors),
        )
