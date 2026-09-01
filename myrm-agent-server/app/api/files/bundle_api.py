"""Deliverable Bundles API routes.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException
- starlette.responses::StreamingResponse
- app.platform_utils.workspace_root::get_workspace_root
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault
- myrm_agent_harness.core.artifacts.manifest::DeliverableManifest, DeliverableItem
- app.services.artifacts.bundle_exporter::BundleExporter

[OUTPUT]
- router: APIRouter — Deliverable Bundles REST API

[POS]
Server API Layer — 提供交付包 Manifest 查询、创建/登记与流式 ZIP 打包下载。
"""

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.core.artifacts.manifest import DeliverableItem, DeliverableManifest
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.platform_utils.workspace_root import get_workspace_root
from app.services.artifacts.bundle_exporter import BundleExporter

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateBundleRequest(BaseModel):
    bundle_id: str
    session_id: str
    title: str
    task_prompt: str = ""
    agent_id: str = ""
    items: list[DeliverableItem] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def _get_vault() -> ArtifactVault:
    workspace_root = get_workspace_root()
    return ArtifactVault(str(workspace_root))


@router.get("/bundles/{bundle_id}", response_model=DeliverableManifest)
async def get_deliverable_bundle_manifest(
    bundle_id: str,
    vault: ArtifactVault = Depends(_get_vault),
) -> DeliverableManifest:
    """获取指定交付包的结构化清单 (Manifest)"""
    data = vault.get_manifest(bundle_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deliverable bundle not found: {bundle_id}")

    try:
        return DeliverableManifest.model_validate(data)
    except Exception as e:
        logger.error("Failed to parse manifest %s: %s", bundle_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Corrupted manifest data") from e


@router.post("/bundles", response_model=DeliverableManifest)
async def create_or_register_bundle(
    payload: CreateBundleRequest,
    vault: ArtifactVault = Depends(_get_vault),
) -> DeliverableManifest:
    """创建或持久化交付包清单"""
    manifest = DeliverableManifest(
        bundle_id=payload.bundle_id,
        session_id=payload.session_id,
        title=payload.title,
        task_prompt=payload.task_prompt,
        agent_id=payload.agent_id,
        items=payload.items,
        metadata=payload.metadata,
    )

    vault.save_manifest(manifest.model_dump())
    return manifest


@router.get("/bundles/{bundle_id}/zip")
async def download_bundle_zip(
    bundle_id: str,
    vault: ArtifactVault = Depends(_get_vault),
) -> StreamingResponse:
    """流式下载成套交付物 ZIP 压缩包 (恒定 <1MB 内存占用)"""
    data = vault.get_manifest(bundle_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deliverable bundle not found: {bundle_id}")

    try:
        manifest = DeliverableManifest.model_validate(data)
    except Exception as e:
        logger.error("Failed to parse manifest %s: %s", bundle_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Corrupted manifest data") from e

    # 空包安全判定
    if not manifest.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot export empty deliverable bundle")

    exporter = BundleExporter(vault)
    filename = f"{manifest.title or 'deliverables'}_{manifest.bundle_id[:8]}.zip"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        exporter.stream_zip(manifest),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Cache-Control": "no-cache",
            "X-Deliverable-Bundle-Id": manifest.bundle_id,
        },
    )
