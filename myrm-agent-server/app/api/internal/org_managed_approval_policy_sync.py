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

from fastapi import APIRouter, HTTPException, Request
from myrm_agent_harness.api.security import (
    ManagedApprovalPolicy,
    configure_process_managed_approval_policy,
    get_process_managed_approval_policy,
    get_process_managed_approval_revision,
)
from pydantic import BaseModel, Field

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)
router = APIRouter()

_CP_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_CP_TOKEN_HEADER = "X-Telemetry-Token"


class OrgManagedApprovalPolicySyncRequest(BaseModel):
    ignoreAllowlistForModels: list[str] = Field(default_factory=list)
    forceAutoReviewForModels: list[str] = Field(default_factory=list)
    disableYolo: bool = False
    disableAllowAlways: bool = False


class OrgManagedApprovalPolicySyncResponse(BaseModel):
    status: str = "synced"
    active: bool = False


def _verify_cp_token(request: Request) -> None:
    expected = os.environ.get(_CP_TOKEN_ENV)
    if not expected:
        return
    token = request.headers.get(_CP_TOKEN_HEADER, "")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid CP token")


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
    request: Request,
    body: OrgManagedApprovalPolicySyncRequest,
) -> OrgManagedApprovalPolicySyncResponse:
    """Receive org MAP from Control Plane and apply to the running agent-server process."""
    _verify_cp_token(request)

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
