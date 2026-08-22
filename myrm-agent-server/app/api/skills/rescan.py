"""Skill supply chain rescan and advisory governance endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.skills._deploy_capability import require_local_skills_capability
from app.api.skills.rescan_schemas import (
    AdvisoryAckRequest,
    AdvisoryAckResponse,
    AdvisoryUnackRequest,
    RescanReportResponse,
    RescanTriggerRequest,
    SkillRescanItemResponse,
)
from app.core.skills.discovery.rescan_service import rescan_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/rescan", response_model=RescanReportResponse, summary="Trigger supply chain rescan on installed skills")
async def trigger_skill_rescan(
    request: RescanTriggerRequest,
    user_id: str = Query(default="default", description="User ID"),
) -> RescanReportResponse:
    """Execute supply chain and code security rescan on installed skills."""
    require_local_skills_capability()
    try:
        report = await rescan_service.rescan_skills(
            user_id=user_id,
            skill_id=request.skill_id,
            enable_online_osv=request.enable_online_osv,
            auto_quarantine=request.auto_quarantine,
        )
        return RescanReportResponse(
            total_scanned=report.total_scanned,
            clean_count=report.clean_count,
            quarantined_count=report.quarantined_count,
            items=[
                SkillRescanItemResponse(
                    skill_name=item.skill_name,
                    recommendation=item.recommendation,
                    is_clean=item.is_clean,
                    has_critical_or_malware=item.has_critical_or_malware,
                    quarantined=item.quarantined,
                    summary=item.summary,
                    declared_dependencies_count=item.declared_dependencies_count,
                    unacked_advisories_count=item.unacked_advisories_count,
                    acked_advisories_count=item.acked_advisories_count,
                    findings_count=item.findings_count,
                )
                for item in report.items
            ],
        )
    except Exception as exc:
        logger.error("Failed to execute skill rescan: %s", exc)
        raise HTTPException(status_code=500, detail=f"Skill rescan failed: {exc}") from exc


@router.get("/rescan/report", response_model=RescanReportResponse | None, summary="Get last completed rescan report")
async def get_last_rescan_report() -> RescanReportResponse | None:
    """Get the last completed skill rescan report if available."""
    report = rescan_service.get_last_report()
    if report is None:
        return None

    return RescanReportResponse(
        total_scanned=report.total_scanned,
        clean_count=report.clean_count,
        quarantined_count=report.quarantined_count,
        items=[
            SkillRescanItemResponse(
                skill_name=item.skill_name,
                recommendation=item.recommendation,
                is_clean=item.is_clean,
                has_critical_or_malware=item.has_critical_or_malware,
                quarantined=item.quarantined,
                summary=item.summary,
                declared_dependencies_count=item.declared_dependencies_count,
                unacked_advisories_count=item.unacked_advisories_count,
                acked_advisories_count=item.acked_advisories_count,
                findings_count=item.findings_count,
            )
            for item in report.items
        ],
    )


@router.post("/advisories/ack", response_model=AdvisoryAckResponse, summary="Acknowledge a security advisory")
async def ack_security_advisory(request: AdvisoryAckRequest) -> AdvisoryAckResponse:
    """Acknowledge / dismiss a security advisory finding."""
    ack = rescan_service.ack_advisory(
        advisory_id=request.advisory_id,
        package_name=request.package_name,
        reason=request.reason,
        acked_by=request.acked_by,
    )
    return AdvisoryAckResponse(
        advisory_id=ack.advisory_id,
        package_name=ack.package_name,
        reason=ack.reason,
        acked_at=ack.acked_at,
        acked_by=ack.acked_by,
    )


@router.post("/advisories/unack", summary="Un-acknowledge a security advisory")
async def unack_security_advisory(request: AdvisoryUnackRequest) -> dict[str, bool]:
    """Reinstate an advisory finding by removing its acknowledgment."""
    success = rescan_service.unack_advisory(
        advisory_id=request.advisory_id,
        package_name=request.package_name,
    )
    return {"success": success}


@router.get("/advisories/acks", response_model=list[AdvisoryAckResponse], summary="List all acknowledged advisories")
async def list_acknowledged_advisories() -> list[AdvisoryAckResponse]:
    """List all registered advisory acknowledgments."""
    acks = rescan_service.list_acks()
    return [
        AdvisoryAckResponse(
            advisory_id=ack.advisory_id,
            package_name=ack.package_name,
            reason=ack.reason,
            acked_at=ack.acked_at,
            acked_by=ack.acked_by,
        )
        for ack in acks
    ]
