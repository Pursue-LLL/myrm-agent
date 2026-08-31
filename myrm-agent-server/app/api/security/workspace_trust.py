"""Workspace trust REST API — FolderGate manifest + trust decisions.

[INPUT]
- app.services.security.workspace_trust_store::get_workspace_trust_store (POS: UserConfig-backed registry)
- myrm_agent_harness.agent.security.workspace_trust::manifest_hash (POS: audit hash helper)

[OUTPUT]
- POST /manifest: pre-bind disclosure payload
- POST /decide: persist TRUSTED / RESTRICTED decision
- GET /: list trusted folders
- DELETE /: revoke or remove entry

[POS]
Settings + FolderGate REST surface. Harness resolves trust via startup lookup injection.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel
from pydantic import BaseModel, Field

from app.core.utils.errors import not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.services.security.workspace_trust_store import get_workspace_trust_store

router = APIRouter()


class ManifestRequest(BaseModel):
    path: str = Field(..., min_length=1)


class DecideRequest(BaseModel):
    path: str = Field(..., min_length=1)
    level: Literal["TRUSTED", "RESTRICTED"]
    manifest_hash: str | None = None


def _manifest_to_dict(manifest: object) -> dict[str, object]:
    from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustManifest

    if not isinstance(manifest, WorkspaceTrustManifest):
        return {}
    return {
        "path": manifest.path,
        "canonical_path": manifest.canonical_path,
        "skill_count": manifest.skill_count,
        "rule_count": manifest.rule_count,
        "repo_command_prefixes": list(manifest.repo_command_prefixes),
        "has_myrm_config": manifest.has_myrm_config,
        "current_level": manifest.current_level.value if manifest.current_level else None,
    }


def _entry_to_dict(entry: object) -> dict[str, object]:
    from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustEntry

    if not isinstance(entry, WorkspaceTrustEntry):
        return {}
    return {
        "path": entry.path,
        "level": entry.level.value,
        "decided_at": entry.decided_at,
        "manifest_hash": entry.manifest_hash,
    }


@router.post("/manifest")
async def preview_manifest(body: ManifestRequest) -> JSONResponse:
    store = get_workspace_trust_store()
    if not store.loaded:
        await store.load()
    try:
        manifest = await store.build_manifest(body.path)
    except ValueError as exc:
        raise validation_error(str(exc)) from exc
    return success_response(data=_manifest_to_dict(manifest))


@router.post("/decide")
async def decide_trust(body: DecideRequest) -> JSONResponse:
    store = get_workspace_trust_store()
    if not store.loaded:
        await store.load()
    try:
        manifest = await store.build_manifest(body.path)
    except ValueError as exc:
        raise validation_error(str(exc)) from exc

    from myrm_agent_harness.agent.security.workspace_trust.manifest import manifest_hash

    expected_hash = manifest_hash(manifest)
    if body.manifest_hash and body.manifest_hash != expected_hash:
        raise validation_error("Folder contents changed since preview. Review again before trusting.")

    level = WorkspaceTrustLevel(body.level)
    entry = await store.decide(body.path, level, manifest=manifest)
    return success_response(data=_entry_to_dict(entry))


@router.get("")
async def list_trusted_folders() -> JSONResponse:
    store = get_workspace_trust_store()
    if not store.loaded:
        await store.load()
    entries = store.list_entries()
    return success_response(data=[_entry_to_dict(entry) for entry in entries])


@router.delete("")
async def revoke_trusted_folder(
    path: str = Query(..., min_length=1),
    *,
    remove: bool = Query(False, description="When true, delete the entry instead of marking REVOKED"),
) -> JSONResponse:
    store = get_workspace_trust_store()
    if not store.loaded:
        await store.load()
    try:
        if remove:
            removed = await store.remove(path)
            if not removed:
                raise not_found_error("Trusted folder")
            return success_response(data={"removed": True})
        entry = await store.revoke(path)
    except ValueError as exc:
        raise validation_error(str(exc)) from exc

    if entry is None:
        raise not_found_error("Trusted folder")
    return success_response(data=_entry_to_dict(entry))
