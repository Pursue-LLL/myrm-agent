"""Control Plane → sandbox Managed Approval Policy (MAP) sync endpoint.

[INPUT]
- CP pushes organization-level MAP JSON via this internal API

[OUTPUT]
- POST /api/admin/org-managed-approval-policy-sync: updates process-wide MAP

[POS]
Receives org approval floor from Control Plane and applies via harness configure hook.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.api.security import (
    ManagedApprovalPolicy,
    configure_process_managed_approval_policy,
    get_process_managed_approval_policy,
    get_process_managed_approval_revision,
)
from pydantic import BaseModel, Field

from app.core.security.auth.control_plane_guard import verify_control_plane_token
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_control_plane_token)])


class OrgManagedApprovalPolicySyncRequest(BaseModel):
    ignoreAllowlistForModels: list[str] = Field(default_factory=list)
    forceAutoReviewForModels: list[str] = Field(default_factory=list)
    disableYolo: bool = False
    disableAllowAlways: bool = False


class OrgManagedApprovalPolicySyncResponse(BaseModel):
    status: str = "synced"
    active: bool = False


def _notify_managed_policy_updated(revision: int, active: bool) -> None:
    try:
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.MANAGED_POLICY_UPDATED,
                data={"revision": revision, "active": active},
            )
        )
    except Exception:
        logger.exception("Failed to publish managed policy updated event")


@router.post(
    "/api/admin/org-managed-approval-policy-sync",
    response_model=OrgManagedApprovalPolicySyncResponse,
)
async def org_managed_approval_policy_sync(
    body: OrgManagedApprovalPolicySyncRequest,
) -> OrgManagedApprovalPolicySyncResponse:
    """Receive org MAP from Control Plane and apply to the running agent-server process."""
    policy = ManagedApprovalPolicy.from_mapping(body.model_dump())
    configure_process_managed_approval_policy(policy)
    active = get_process_managed_approval_policy() != ManagedApprovalPolicy.empty()
    revision = get_process_managed_approval_revision()
    _notify_managed_policy_updated(revision, active)
    logger.info(
        "Org managed approval policy sync: active=%s ignore=%d force=%d",
        active,
        len(body.ignoreAllowlistForModels),
        len(body.forceAutoReviewForModels),
    )
    return OrgManagedApprovalPolicySyncResponse(status="synced", active=active)
