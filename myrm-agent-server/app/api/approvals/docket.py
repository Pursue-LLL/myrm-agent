"""[INPUT]
- app.services.approvals.docket_service::DocketService (POS: 法律案卷包检索与构建服务)
- app.services.approvals.registry::ApprovalRegistry (POS: 统一审批单持久化服务)

[OUTPUT]
- GET /approvals/{approval_id}/docket: 获取结构化法律案卷包详情
- GET /approvals/{approval_id}/docket/export: 一键导出 JSON-LD 合规卷宗档案

[POS]
提供面向法务合规专员与外部审计员的结构化案卷查询与一键法律证据导出接口。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from app.services.approvals.docket_service import DocketService
from app.services.approvals.registry import ApprovalRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals-docket"])


class DocketResponse(BaseModel):
    docket_id: str
    action_type: str
    root_digest: str
    signature: dict[str, object] | None
    triad_proof: dict[str, object]
    input_summary: str
    output_summary: str
    asset_fingerprints_count: int
    created_at: float
    metadata: dict[str, str]


@router.get("/{approval_id}/docket", response_model=DocketResponse)
async def get_approval_audit_docket(approval_id: str) -> DocketResponse:
    """Retrieve the sealed legal audit docket for a resolved approval record."""
    docket = DocketService.get_docket(approval_id)
    if not docket:
        # If not cached, check if approval exists and generate on-demand
        record = await ApprovalRegistry.get_approval(approval_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
        docket = await DocketService.create_docket_for_approval(record)

    return DocketResponse(
        docket_id=docket.docket_id,
        action_type=docket.action_type,
        root_digest=docket.root_digest,
        signature=docket.signature.to_dict() if docket.signature else None,
        triad_proof=docket.triad_proof.to_dict(),
        input_summary=docket.input_summary,
        output_summary=docket.output_summary,
        asset_fingerprints_count=len(docket.asset_fingerprints),
        created_at=docket.created_at,
        metadata=docket.metadata,
    )


@router.get("/{approval_id}/docket/export")
async def export_approval_audit_docket(approval_id: str) -> Response:
    """Export the sealed legal audit docket in JSON-LD format for external verification."""
    docket = DocketService.get_docket(approval_id)
    if not docket:
        record = await ApprovalRegistry.get_approval(approval_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
        docket = await DocketService.create_docket_for_approval(record)

    json_ld_content = docket.to_export_json_ld()
    return Response(
        content=json_ld_content,
        media_type="application/ld+json",
        headers={
            "Content-Disposition": f'attachment; filename="audit_docket_{approval_id}.jsonld"',
        },
    )
