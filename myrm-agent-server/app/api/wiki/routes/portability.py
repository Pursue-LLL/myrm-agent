"""[INPUT]
- app.api.wiki.archiver_dependency::get_scoped_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault files use ``app.services.wiki.vault.get_wiki_structure`` instead, so no compile worker is ever built without a model.)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian / source_sync / clip / knowledge_pack) live under this package and expose their own facades.)

[OUTPUT]
- export_wiki_vault: Export the full wiki vault as an Obsidian-ready ZIP (raw + wiki + graph preset).

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import asyncio
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.services.wiki import MemoryToWikiArchiver

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


@router.get("/portability/export")
async def export_wiki_vault(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to export")] = None,
) -> StreamingResponse:
    """Export the full wiki vault as an Obsidian-ready ZIP (raw + wiki + graph preset)."""
    from myrm_agent_harness.toolkits.wiki.portability.vault_archive import (
        iter_vault_files,
    )

    from app.services.wiki.vault import build_wiki_export_zip

    structure = archiver._structure
    if not iter_vault_files(structure):
        raise HTTPException(status_code=400, detail="Wiki vault is empty")
    try:
        memory_file = await asyncio.to_thread(build_wiki_export_zip, structure, agent_id)
        scope = agent_id or "default"
        filename = f"myrm_wiki_obsidian_{scope}.zip"

        def iterfile() -> Iterator[bytes]:
            yield memory_file.read()

        return StreamingResponse(
            iterfile(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Wiki vault export failed: %s", e)
        raise HTTPException(status_code=500, detail="Wiki vault export failed") from e
