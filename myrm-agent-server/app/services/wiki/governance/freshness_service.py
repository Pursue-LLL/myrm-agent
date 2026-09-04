"""Wiki knowledge governance freshness, archive, and revival domain service.

[INPUT]
- pathlib::Path
- app.services.wiki.governance.schemas::*
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure
- myrm_agent_harness.toolkits.wiki.retrieval.indexer::WikiIndexer

[OUTPUT]
- WikiGovernanceFreshnessService: Core business service for freshness scanning, safe archive, and revival.

[POS]
Domain service powering the Knowledge Governance Workbench.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.wiki.governance.schemas import (
    ExpiringConceptInfo,
    GovernanceActionResult,
    GovernanceOverviewResult,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
    from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

logger = logging.getLogger(__name__)

# In-memory undo buffer: undo_token -> (timestamp, list_of_archived_concept_names)
_UNDO_BUFFER_TTL_SECONDS = 30.0
_undo_store: dict[str, tuple[float, list[str]]] = {}


def _cleanup_expired_undo_tokens() -> None:
    now = time.monotonic()
    expired = [t for t, (ts, _) in _undo_store.items() if now - ts > _UNDO_BUFFER_TTL_SECONDS]
    for t in expired:
        _undo_store.pop(t, None)


def _is_concept_permanent(file_path: Path) -> bool:
    """Check if concept frontmatter declares permanent/pinned lifecycle."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if not content.startswith("---"):
            return False
        parts = content.split("---", 2)
        if len(parts) < 3:
            return False
        frontmatter = parts[1].lower()
        if "lifecycle: permanent" in frontmatter or "lifecycle: evergreen" in frontmatter:
            return True
        if "pinned: true" in frontmatter or "permanent: true" in frontmatter:
            return True
    except Exception as exc:
        logger.debug("Failed to read frontmatter for %s: %s", file_path, exc)
    return False


class WikiGovernanceFreshnessService:
    """Core domain service for knowledge freshness scanning, safe archiving, and revival."""

    def __init__(
        self,
        structure: WikiStructure,
        indexer: WikiIndexer | None = None,
        *,
        freshness_threshold_days: int = 90,
    ) -> None:
        self._structure = structure
        self._indexer = indexer
        self._threshold_days = freshness_threshold_days

    def scan_expiring_concepts(self) -> list[ExpiringConceptInfo]:
        """Scan active concepts for items exceeding freshness threshold (default 90 days)."""
        expiring: list[ExpiringConceptInfo] = []
        now = datetime.now(tz=UTC)
        now_ts = now.timestamp()

        # Only scan local writable concepts_dir (public_dirs are strictly read-only and preserved)
        if not self._structure.concepts_dir.exists():
            return expiring

        for md_file in sorted(self._structure.concepts_dir.rglob("*.md")):
            if self._structure._is_directory_sidecar(md_file):
                continue

            try:
                stat = md_file.stat()
                mtime = stat.st_mtime
                age_days = int((now_ts - mtime) // 86400)
                is_perm = _is_concept_permanent(md_file)

                rel = md_file.relative_to(self._structure.concepts_dir)
                concept_name = str(rel.with_suffix("")).replace("\\", "/")

                if is_perm:
                    continue

                if age_days >= self._threshold_days:
                    dt = datetime.fromtimestamp(mtime, tz=UTC)
                    expiring.append(
                        ExpiringConceptInfo(
                            concept_name=concept_name,
                            relative_path=str(rel),
                            age_days=age_days,
                            modified_at_iso=dt.isoformat(),
                            is_permanent=False,
                            reason=f"Unchanged for {age_days} days (threshold: {self._threshold_days}d)",
                        )
                    )
            except Exception as exc:
                logger.debug("Failed to inspect concept %s: %s", md_file, exc)

        return sorted(expiring, key=lambda c: c.age_days, reverse=True)

    def scan_archived_concepts(self) -> list[ExpiringConceptInfo]:
        """Scan isolated archive directory for archived concepts."""
        archived: list[ExpiringConceptInfo] = []
        if not self._structure.archive_dir.exists():
            return archived

        for md_file in sorted(self._structure.archive_dir.rglob("*.md")):
            if self._structure._is_directory_sidecar(md_file):
                continue

            try:
                stat = md_file.stat()
                mtime = stat.st_mtime
                age_days = int((time.time() - mtime) // 86400)
                rel = md_file.relative_to(self._structure.archive_dir)
                concept_name = str(rel.with_suffix("")).replace("\\", "/")
                dt = datetime.fromtimestamp(mtime, tz=UTC)

                archived.append(
                    ExpiringConceptInfo(
                        concept_name=concept_name,
                        relative_path=str(rel),
                        age_days=age_days,
                        modified_at_iso=dt.isoformat(),
                        is_permanent=False,
                        reason="Archived",
                    )
                )
            except Exception as exc:
                logger.debug("Failed to inspect archived concept %s: %s", md_file, exc)

        return archived

    def get_governance_overview(
        self,
        *,
        pending_count: int = 0,
        gaps_count: int = 0,
    ) -> GovernanceOverviewResult:
        """Aggregate four-queue governance overview."""
        expiring = self.scan_expiring_concepts()
        archived = self.scan_archived_concepts()
        total_active = len(self._structure.list_concepts())

        return GovernanceOverviewResult(
            pending_count=pending_count,
            expiring_count=len(expiring),
            gaps_count=gaps_count,
            archived_count=len(archived),
            total_active=total_active,
            expiring_concepts=expiring,
            archived_concepts=archived,
        )

    def extend_concepts(self, concept_names: list[str]) -> GovernanceActionResult:
        """Reset the expiration clock on concepts by touching their mtime."""
<<<<<<< HEAD
        now = time.time()
=======
>>>>>>> bd6468f71 (fix(arch): register device domain in SERVICES_ONLY_DOMAINS)
        success_count = 0
        for name in concept_names:
            path = self._structure.get_concept_file_path(name)
            if path.exists():
                try:
                    # Update modification time to now
                    path.touch()
                    success_count += 1
                except Exception as exc:
                    logger.warning("Failed to extend concept %s: %s", name, exc)

        return GovernanceActionResult(
            success=success_count > 0,
            affected_count=success_count,
            message=f"Extended {success_count} concept(s) by {self._threshold_days} days",
        )

    async def archive_concepts(
        self,
        concept_names: list[str],
        *,
        reason: str = "",
    ) -> GovernanceActionResult:
        """Atomically move concepts into archive directory and register undo buffer."""
        _cleanup_expired_undo_tokens()
        archived_names: list[str] = []

        for name in concept_names:
            try:
                await self._structure.archive_concept_safe(name, indexer=self._indexer, reason=reason)
                archived_names.append(name)
            except Exception as exc:
                logger.warning("Failed to archive concept %s: %s", name, exc)

        undo_token = ""
        if archived_names:
            undo_token = str(uuid.uuid4())
            _undo_store[undo_token] = (time.monotonic(), archived_names)

        return GovernanceActionResult(
            success=len(archived_names) > 0,
            affected_count=len(archived_names),
            message=f"Archived {len(archived_names)} concept(s)",
            undo_token=undo_token,
        )

    async def undo_archive(self, undo_token: str) -> GovernanceActionResult:
        """Undo a recent batch archive operation within 30-second window."""
        _cleanup_expired_undo_tokens()
        entry = _undo_store.pop(undo_token, None)
        if not entry:
            return GovernanceActionResult(
                success=False,
                affected_count=0,
                message="Undo token expired or not found",
            )

        _, names = entry
        revived_count = 0
        for name in names:
            try:
                await self._structure.revive_concept_safe(name, indexer=self._indexer)
                revived_count += 1
            except Exception as exc:
                logger.warning("Failed to undo archive for concept %s: %s", name, exc)

        return GovernanceActionResult(
            success=revived_count > 0,
            affected_count=revived_count,
            message=f"Undid archive for {revived_count} concept(s)",
        )

    async def revive_concepts(self, concept_names: list[str]) -> GovernanceActionResult:
        """Revive archived concepts back into active concepts directory."""
        revived_count = 0
        for name in concept_names:
            try:
                await self._structure.revive_concept_safe(name, indexer=self._indexer)
                revived_count += 1
            except Exception as exc:
                logger.warning("Failed to revive concept %s: %s", name, exc)

        return GovernanceActionResult(
            success=revived_count > 0,
            affected_count=revived_count,
            message=f"Revived {revived_count} concept(s) to active knowledge base",
        )
