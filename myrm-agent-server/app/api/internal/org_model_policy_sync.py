"""Control Plane → sandbox Org Model Policy sync endpoint.

[INPUT]
- CP pushes organization-level model policy (allowed patterns) via this internal API

[OUTPUT]
- POST /api/admin/org-model-policy-sync: Stores allowed patterns in UserConfig table
- GET /api/v1/org-policy/allowed-models: Exposes patterns to frontend for model filtering (via frontend_router)

[POS]
Receives org model whitelist from Control Plane and persists locally.
Frontend reads this to grey-out restricted models in the model selector.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.services.config.service import ConfigService

logger = logging.getLogger(__name__)
router = APIRouter()

_CP_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_CP_TOKEN_HEADER = "X-Telemetry-Token"
_ORG_MODEL_POLICY_KEY = "orgModelPolicy"


class OrgModelPolicySyncRequest(BaseModel):
    allowed_patterns: list[str]


class OrgModelPolicySyncResponse(BaseModel):
    status: str = "synced"
    pattern_count: int = 0


class AllowedModelsResponse(BaseModel):
    allowed_patterns: list[str]
    restricted: bool = False


def _verify_cp_token(request: Request) -> None:
    expected = os.environ.get(_CP_TOKEN_ENV)
    if not expected:
        return
    token = request.headers.get(_CP_TOKEN_HEADER, "")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid CP token")


@router.post("/api/admin/org-model-policy-sync", response_model=OrgModelPolicySyncResponse)
async def org_model_policy_sync(
    request: Request, body: OrgModelPolicySyncRequest
) -> OrgModelPolicySyncResponse:
    """Receive org model policy from Control Plane and persist locally."""
    _verify_cp_token(request)

    config_svc = ConfigService()
    await config_svc.set(
        config_key=_ORG_MODEL_POLICY_KEY,
        value={"allowed_patterns": body.allowed_patterns},
        device_id="control_plane",
    )

    invalidate_user_configs_cache()
    logger.info("Org model policy sync: %d patterns", len(body.allowed_patterns))
    return OrgModelPolicySyncResponse(
        status="synced", pattern_count=len(body.allowed_patterns)
    )


frontend_router = APIRouter()


@frontend_router.get("/org-policy/allowed-models", response_model=AllowedModelsResponse)
async def get_allowed_models() -> AllowedModelsResponse:
    """Frontend-facing: get org model policy for UI filtering."""
    config_svc = ConfigService()
    record = await config_svc.get(_ORG_MODEL_POLICY_KEY)
    if record is None:
        return AllowedModelsResponse(allowed_patterns=[], restricted=False)

    patterns = record.value.get("allowed_patterns", []) if isinstance(record.value, dict) else []
    return AllowedModelsResponse(
        allowed_patterns=patterns,
        restricted=len(patterns) > 0,
    )
