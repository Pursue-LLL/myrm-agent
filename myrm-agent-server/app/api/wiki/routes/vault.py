"""Wiki vault 在文件管理器中打开的路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes.schemas import (
    OperationResult,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


@router.post("/vault/reveal", response_model=OperationResult)
async def reveal_wiki_vault(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Reveal the agent wiki vault folder in the local file manager (local mode only)."""
    from app.config.deploy_mode import is_local_mode
    from app.services.files.reveal_utils import reveal_path_in_file_manager

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="Vault reveal is only available in local mode")

    vault_path = archiver.get_wiki_path().resolve()
    if not vault_path.is_dir():
        raise HTTPException(status_code=404, detail="Wiki vault directory not found")

    reveal_path_in_file_manager(vault_path)
    return OperationResult(success=True, message=str(vault_path))


@router.post("/vault/open-obsidian", response_model=OperationResult)
async def open_wiki_vault_in_obsidian(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Open the wiki vault in Obsidian when available, otherwise reveal the folder (local mode only)."""
    from app.config.deploy_mode import is_local_mode
    from app.services.files.reveal_utils import (
        open_vault_in_obsidian_app,
        reveal_path_in_file_manager,
    )

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="Obsidian open is only available in local mode")

    vault_path = archiver.get_wiki_path().resolve()
    if not vault_path.is_dir():
        raise HTTPException(status_code=404, detail="Wiki vault directory not found")

    if open_vault_in_obsidian_app(vault_path):
        return OperationResult(success=True, message=str(vault_path))

    reveal_path_in_file_manager(vault_path)
    return OperationResult(success=True, message=str(vault_path))
