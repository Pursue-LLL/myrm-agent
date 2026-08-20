"""Local-only wiki provenance gap Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.wiki.vault::get_wiki_archiver (POS: shared wiki vault accessor)
- app.services.wiki.structural_stats_cache::invalidate_structural_lint_cache (POS: stats TTL bust)

[OUTPUT]
- router: POST /test/seed-wiki-provenance-gap-fixture (POS: E2E seed endpoint)

[POS]
Chats API local test fixture. Seeds a compiled concept missing sources for health report Chrome E2E.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.config.deploy_mode import is_local_mode

router = APIRouter()


@router.post("/test/seed-wiki-provenance-gap-fixture", include_in_schema=False)
async def seed_wiki_provenance_gap_fixture(
    agent_id: str | None = Query(default=None, description="Optional agent wiki vault scope"),
) -> dict[str, object]:
    """Local dev/test only: write a concept with missing raw-backed provenance."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from myrm_agent_harness.toolkits.wiki.diagnostics.structural_lint import (
        collect_provenance_gap_issues,
    )

    from app.services.wiki.structural_stats_cache import invalidate_structural_lint_cache
    from app.services.wiki.vault import get_wiki_archiver

    suffix = uuid4().hex[:8]
    archiver = get_wiki_archiver(None, agent_id=agent_id)
    structure = archiver._structure
    structure.ensure_structure()

    relative_concept = f"e2e-provenance/gap-{suffix}.md"
    concept_path = structure.concepts_dir / relative_concept
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    concept_path.write_text(
        "---\ntitle: Provenance Gap E2E\ntype: concept\nprovenance: compiled\n---\n\nFixture concept missing sources list.\n",
        encoding="utf-8",
    )
    invalidate_structural_lint_cache(structure)

    gaps = collect_provenance_gap_issues(structure)
    matching = [issue for issue in gaps if issue.location.endswith(relative_concept)]
    if not matching:
        raise HTTPException(
            status_code=500,
            detail="Provenance gap seed failed: lint did not detect fixture concept",
        )

    ui_path = "/settings/wiki"
    if agent_id:
        ui_path = f"/settings/wiki?agentId={agent_id}"

    return {
        "agent_id": agent_id,
        "ui_path": ui_path,
        "concept_relative_path": relative_concept,
        "provenance_gaps": len(gaps),
    }
