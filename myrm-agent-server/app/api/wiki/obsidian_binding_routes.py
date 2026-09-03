"""Obsidian Vault declarative binding and delta synchronization API routes.

[INPUT]
- FastAPI router, dependencies (archiver, optional llm/memory)
- app.services.wiki.obsidian.binding (POS: Vault binding & delta calculation)
- app.services.wiki.obsidian.adapter (POS: prepare_obsidian_file)

[OUTPUT]
- GET /vault/binding: Fetch active binding status.
- POST /vault/bind: Set or update local/cloud vault directory.
- POST /vault/unbind: Remove vault binding.
- POST /vault/sync-delta: Trigger incremental mtime sync into the wiki vault.

[POS]
API presentation layer for live Obsidian Vault integration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_optional_llm_for_user, get_optional_memory_manager
from app.services.wiki.obsidian.adapter import prepare_obsidian_file
from app.services.wiki.obsidian.binding import (
    ObsidianVaultBinding,
    get_obsidian_vault_binding,
    scan_vault_mtime_watermark,
    set_obsidian_vault_binding,
)
from app.services.wiki.vault import get_wiki_archiver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vault", tags=["wiki-obsidian-vault"])


class VaultBindingResponse(BaseModel):
    is_bound: bool
    vault_path: str = ""
    is_active: bool = False
    last_sync_watermark: float = 0.0
    auto_sync_on_recall: bool = True
    allow_inbox_write: bool = True
    inbox_folder_name: str = "_Myrm_Inbox"
    updated_at: float = 0.0


class BindVaultRequest(BaseModel):
    vault_path: str = Field(..., description="Absolute path to the local Obsidian Vault")
    auto_sync_on_recall: bool = Field(True, description="Sync delta files before recall")
    allow_inbox_write: bool = Field(True, description="Enable agent write-back to inbox")
    inbox_folder_name: str = Field("_Myrm_Inbox", description="Inbox folder relative name")


class VaultDeltaSyncResponse(BaseModel):
    success: bool
    vault_path: str
    scanned_count: int
    synced_count: int
    skipped_count: int
    synced_files: list[str]
    new_watermark: float
    message: str


@router.get("/binding", response_model=VaultBindingResponse)
async def get_binding() -> VaultBindingResponse:
    """Get active Obsidian vault binding."""
    binding = await get_obsidian_vault_binding()
    if not binding or not binding.is_active or not binding.vault_path:
        return VaultBindingResponse(is_bound=False)

    return VaultBindingResponse(
        is_bound=True,
        vault_path=binding.vault_path,
        is_active=binding.is_active,
        last_sync_watermark=binding.last_sync_watermark,
        auto_sync_on_recall=binding.auto_sync_on_recall,
        allow_inbox_write=binding.allow_inbox_write,
        inbox_folder_name=binding.inbox_folder_name,
        updated_at=binding.updated_at,
    )


@router.post("/bind", response_model=VaultBindingResponse)
async def bind_vault(request: BindVaultRequest) -> VaultBindingResponse:
    """Bind an Obsidian vault directory."""
    raw_path = request.vault_path.strip()
    p = Path(raw_path).expanduser().resolve()
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {request.vault_path}")

    binding = ObsidianVaultBinding(
        vault_path=str(p),
        is_active=True,
        last_sync_watermark=0.0,
        auto_sync_on_recall=request.auto_sync_on_recall,
        allow_inbox_write=request.allow_inbox_write,
        inbox_folder_name=request.inbox_folder_name,
    )
    saved = await set_obsidian_vault_binding(binding)

    return VaultBindingResponse(
        is_bound=True,
        vault_path=saved.vault_path,
        is_active=saved.is_active,
        last_sync_watermark=saved.last_sync_watermark,
        auto_sync_on_recall=saved.auto_sync_on_recall,
        allow_inbox_write=saved.allow_inbox_write,
        inbox_folder_name=saved.inbox_folder_name,
        updated_at=saved.updated_at,
    )


@router.post("/unbind", response_model=VaultBindingResponse)
async def unbind_vault() -> VaultBindingResponse:
    """Unbind current Obsidian vault."""
    binding = await get_obsidian_vault_binding()
    if binding:
        binding.is_active = False
        await set_obsidian_vault_binding(binding)
    return VaultBindingResponse(is_bound=False)


@router.post("/sync-delta", response_model=VaultDeltaSyncResponse)
async def sync_vault_delta(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    llm: Annotated[object | None, Depends(get_optional_llm_for_user)] = None,
    manager: Annotated[object | None, Depends(get_optional_memory_manager)] = None,
) -> VaultDeltaSyncResponse:
    """Scan and incrementally ingest modified/added files since watermark into Wiki raw/."""
    binding = await get_obsidian_vault_binding()
    if not binding or not binding.is_active or not binding.vault_path:
        raise HTTPException(status_code=400, detail="No active Obsidian vault bound")

    vault_root = Path(binding.vault_path)
    if not vault_root.is_dir():
        raise HTTPException(status_code=404, detail=f"Bound vault directory not found: {binding.vault_path}")

    scan_res = scan_vault_mtime_watermark(vault_root, binding.last_sync_watermark)
    if not scan_res.has_changes:
        return VaultDeltaSyncResponse(
            success=True,
            vault_path=binding.vault_path,
            scanned_count=scan_res.total_files_scanned,
            synced_count=0,
            skipped_count=0,
            synced_files=[],
            new_watermark=scan_res.new_watermark,
            message="No changes detected since last sync watermark",
        )

    archiver = get_wiki_archiver(llm, manager, agent_id=agent_id)
    assets_dir = archiver._structure.wiki_dir / "assets"
    enqueued_paths: list[Path] = []
    synced_files: list[str] = []
    skipped_count = 0

    for rel_path_str in scan_res.modified_files:
        src_file = vault_root / rel_path_str
        try:
            prepared = prepare_obsidian_file(src_file, vault_root, assets_dir)
            if prepared is None:
                skipped_count += 1
                continue

            raw_file_path = archiver._structure.get_raw_file_path(prepared.relative_path)
            raw_file_path.parent.mkdir(parents=True, exist_ok=True)
            raw_file_path.write_text(prepared.content, encoding="utf-8")
            enqueued_paths.append(raw_file_path)
            synced_files.append(prepared.relative_path)
        except Exception as exc:
            logger.warning("Failed to prepare delta file %s: %s", rel_path_str, exc)
            skipped_count += 1

    if enqueued_paths:
        archiver._queue.add_batch(enqueued_paths)
        archiver._compiler.start_background_worker()

    # Advance watermark
    binding.last_sync_watermark = scan_res.new_watermark
    await set_obsidian_vault_binding(binding)

    return VaultDeltaSyncResponse(
        success=True,
        vault_path=binding.vault_path,
        scanned_count=scan_res.total_files_scanned,
        synced_count=len(synced_files),
        skipped_count=skipped_count,
        synced_files=synced_files,
        new_watermark=scan_res.new_watermark,
        message=f"Synced {len(synced_files)} modified files into Wiki queue",
    )
