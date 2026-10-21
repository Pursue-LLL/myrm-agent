"""Local-only wiki pending drift Chrome E2E seed/cleanup routes.

The wiki pending-review panel paginates 50 drafts per page and self-heals back
to page 1 when the queue stats drift between page loads. Verifying that flow
in a real browser needs more than one page of drafts plus an external
approval action, which must never touch real user drafts — so this fixture
stages marker-tagged drafts through the real WikiPendingEditsManager (the
backend stays the single sqlite writer) and removes them by marker prefix.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: gate local-only access)
app.services.wiki.vault::get_wiki_archiver (POS: shared wiki vault accessor)
myrm_agent_harness.toolkits.wiki.pipeline.pending::WikiPendingEditsManager (POS: HITL pending draft manager, single DB writer)

[OUTPUT]
seed_pending_drift_fixture: stage N marker-tagged pending drafts (real writer path)
cleanup_pending_drift_fixture: remove every marker-tagged draft and restore COUNT-based stats

[POS]
Chats API local test fixture. Seeds and cleans marker-tagged wiki pending
drafts for the WikiPendingEdits panel pagination + drift self-heal Chrome E2E.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.config.deploy_mode import is_local_mode

router = APIRouter()

# Three pages at 50/page: first batch, one load-more, and a page-3 remainder
# that keeps the load-more control mounted for the drift re-sync click.
DEFAULT_SEED_COUNT = 105
_CONCEPT_PREFIX = "e2e-pending-drift-"


@router.post("/test/seed-pending-drift-fixture", include_in_schema=False)
async def seed_pending_drift_fixture(
    count: int = Query(default=DEFAULT_SEED_COUNT, ge=1, le=200),
) -> dict[str, object]:
    """Local dev/test only: stage marker-tagged pending drafts via the real writer."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from app.services.wiki.vault import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=None)
    pending_mgr = archiver._pending_mgr
    suffix = uuid4().hex[:8]
    edit_ids: list[int] = []
    for index in range(count):
        edit_id = pending_mgr.add_pending_edit(
            f"{_CONCEPT_PREFIX}{suffix}-{index:03d}",
            f"# Drift fixture draft {index}",
            provenance="e2e-drift",
        )
        edit_ids.append(edit_id)
    return {
        "concept_prefix": f"{_CONCEPT_PREFIX}{suffix}",
        "count": count,
        "edit_ids": edit_ids,
        "stats": pending_mgr.get_stats(),
        "ui_path": "/settings/wiki?wikiTab=pendingEdits",
    }


@router.post("/test/cleanup-pending-drift-fixture", include_in_schema=False)
async def cleanup_pending_drift_fixture() -> dict[str, object]:
    """Local dev/test only: delete every marker-tagged draft (any leftover run)."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from app.services.wiki.vault import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=None)
    pending_mgr = archiver._pending_mgr
    # Same-process connection: the backend remains the single sqlite writer.
    with pending_mgr._get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM pending_edits WHERE concept_name LIKE ?",
            (f"{_CONCEPT_PREFIX}%",),
        )
        deleted = cursor.rowcount or 0
    return {"deleted": deleted, "stats": pending_mgr.get_stats()}
