"""Local-only wiki corpus dedup Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.wiki.vault::get_wiki_archiver (POS: shared wiki vault accessor)
- myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup::CorpusDedupScanner (POS: dedup scan engine)

[OUTPUT]
- router: POST /test/seed-wiki-dedup-fixture (POS: E2E seed endpoint)

[POS]
Chats API local test fixture. Seeds duplicate raw files and runs a synchronous dedup scan for Chrome E2E.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
    CorpusDedupScanner,
    GroupStatus,
)

from app.config.deploy_mode import is_local_mode

router = APIRouter()

_DUPLICATE_BODY = "# Wiki dedup E2E fixture\n\nShared duplicate body for Chrome E2E."


@router.post("/test/seed-wiki-dedup-fixture", include_in_schema=False)
async def seed_wiki_dedup_fixture(
    agent_id: str | None = Query(
        default=None, description="Optional agent wiki vault scope"
    ),
) -> dict[str, object]:
    """Local dev/test only: write duplicate raw files and run dedup scan."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from app.services.wiki.vault import get_wiki_archiver

    suffix = uuid4().hex[:8]
    archiver = get_wiki_archiver(None, agent_id=agent_id)
    structure = archiver._structure
    structure.ensure_structure()

    for relative_path in (f"e2e-dedup/a-{suffix}.md", f"e2e-dedup/b-{suffix}.md"):
        path = structure.get_raw_file_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DUPLICATE_BODY, encoding="utf-8")

    scanner = CorpusDedupScanner(structure)
    scan_result = scanner.scan(incremental=False)
    open_groups = scanner.store.list_groups(status=GroupStatus.OPEN)

    ui_path = "/settings/wiki?wikiTab=duplicateReview"
    if agent_id:
        ui_path = f"/settings/wiki?agentId={agent_id}&wikiTab=duplicateReview"

    return {
        "agent_id": agent_id,
        "ui_path": ui_path,
        "files_scanned": scan_result.files_scanned,
        "exact_groups": scan_result.exact_groups,
        "open_groups": len(open_groups),
        "group_ids": [group.group_id for group in open_groups],
    }
