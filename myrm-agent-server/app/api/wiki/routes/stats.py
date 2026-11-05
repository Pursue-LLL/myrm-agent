"""Wiki 统计概览路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes.schemas import (
    WikiAssetIndexStatsResponse,
    WikiDedupStatsResponse,
    WikiMaintainStateResponse,
    WikiStatsResponse,
    WikiStructuralIssuesResponse,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


@router.get("/stats", response_model=WikiStatsResponse)
async def get_wiki_stats(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiStatsResponse:
    try:
        from app.services.wiki.vault import (
            is_legacy_migration_complete,
            is_vault_ready,
        )

        concepts = archiver._structure.list_concepts()
        raw_files = archiver._structure.list_raw_files()
        from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
            count_log_entries,
            hot_updated_at_iso,
        )

        index_path = archiver._structure.get_index_file_path()
        from app.services.files.reveal_utils import is_obsidian_direct_launch_available
        from app.services.wiki.structural_stats_cache import (
            get_structural_lint_snapshot_cached,
        )

        structural_cached = get_structural_lint_snapshot_cached(archiver._structure)
        structural = structural_cached.snapshot
        from app.services.wiki.asset_index_service import (
            ensure_archiver_asset_indexer,
            wiki_asset_index_enabled,
        )
        from app.services.wiki.vault import read_vault_git_status

        await ensure_archiver_asset_indexer(archiver)
        asset_enabled = await wiki_asset_index_enabled()
        if archiver._asset_indexer is not None:
            asset_stats = archiver._asset_indexer.get_stats()
            asset_index = WikiAssetIndexStatsResponse(
                indexed=asset_stats.indexed,
                pending=asset_stats.pending,
                failed=asset_stats.failed,
                total_files=asset_stats.total_files,
                enabled=True,
            )
        else:
            assets_dir = archiver._structure.wiki_dir / "assets"
            total_files = len([p for p in assets_dir.iterdir() if p.is_file()]) if assets_dir.is_dir() else 0
            asset_index = WikiAssetIndexStatsResponse(
                total_files=total_files,
                pending=total_files,
                enabled=asset_enabled,
            )
        git_status = read_vault_git_status(archiver._structure, archiver._config)
        from app.database.connection import get_session
        from app.services.wiki.maintain import load_wiki_maintain_state

        async with get_session() as db:
            maintain = await load_wiki_maintain_state(db, agent_id=agent_id)
        maintain_state = WikiMaintainStateResponse(
            last_run_at=(maintain.last_run_at.isoformat() if maintain.last_run_at else None),
            last_mode=maintain.last_mode,
            last_issues_found=maintain.last_issues_found,
            last_issues_fixed=maintain.last_issues_fixed,
            last_connections_discovered=maintain.last_connections_discovered,
            last_duration_ms=maintain.last_duration_ms,
            last_skipped_reason=maintain.last_skipped_reason,
        )
        from app.services.wiki.dedup_runner import (
            get_wiki_dedup_stats,
            wiki_dedup_blocks_compile,
        )

        dedup = get_wiki_dedup_stats(agent_id=agent_id)
        dedup_stats = WikiDedupStatsResponse(
            duplicate_groups_pending=dedup.duplicate_groups_pending,
            compile_jobs_prevented=dedup.compile_jobs_prevented,
            eligible_raw_count=dedup.eligible_raw_count,
            excluded_raw_count=dedup.excluded_raw_count,
            trashed_raw_count=dedup.trashed_raw_count,
            blocks_compile=wiki_dedup_blocks_compile(agent_id=agent_id),
        )
        return WikiStatsResponse(
            total_concepts=len(concepts),
            total_articles=len(concepts),
            total_raw_files=len(raw_files),
            wiki_path=str(archiver.get_wiki_path()),
            vault_ready=is_vault_ready(agent_id),
            legacy_migrated=is_legacy_migration_complete(),
            cognitive_index_ready=index_path.exists(),
            cognitive_log_entries=count_log_entries(archiver._structure),
            cognitive_hot_updated_at=hot_updated_at_iso(archiver._structure),
            synthesis_pending=archiver._pending_mgr.count_synthesis_pending(),
            obsidian_launch_available=is_obsidian_direct_launch_available(),
            vault_git_enabled=git_status.enabled,
            vault_git_initialized=git_status.initialized,
            vault_git_last_commit=git_status.last_commit,
            structural_issues=WikiStructuralIssuesResponse(
                broken_links=structural.broken_links,
                invalid_frontmatter_types=structural.invalid_frontmatter_types,
                provenance_gaps=structural.provenance_gaps,
                scanned_concepts=structural.scanned_concepts,
            ),
            dedup_stats=dedup_stats,
            maintain_state=maintain_state,
            asset_index=asset_index,
        )
    except Exception as e:
        logger.error("Wiki full state retrieval failed: %s", e)
        raise HTTPException(status_code=500, detail="Wiki state retrieval failed") from e


# --- Concepts CRUD Endpoints ---
