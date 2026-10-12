"""API router for Causal Deception Defense & Mechanism Probe.

[INPUT]
- AuditCausalConsistencyRequest, AudienceProbeRequest.

[OUTPUT]
- Endpoints for evaluating commitment-execution-report invariance and
  counterfactual audience vulnerability probes.

[POS]
- Server API. Mounted under /api/v1/security/causal-deception.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.causal_deception import (
    AudienceProbeRequest,
    AudienceProbeResponse,
    AuditCausalConsistencyRequest,
    AuditCausalConsistencyResponse,
)
from app.services.security.causal_deception_service import (
    get_causal_deception_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/causal-deception", tags=["causal-deception"])


@router.post("/audit", response_model=AuditCausalConsistencyResponse)
def audit_causal_consistency(req: AuditCausalConsistencyRequest) -> AuditCausalConsistencyResponse:
    """Evaluate whether post-report claims are causally grounded in actual physical tool traces."""
    service = get_causal_deception_service()
    resp = service.audit_consistency(req)

    if req.fail_closed and not resp.is_consistent and resp.overall_verdict == "DECEPTIVE_FABRICATION":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Causal Deception Interception: Detected {len(resp.violations)} fabricated assertions.",
        )

    return resp


@router.post("/probe-audience", response_model=AudienceProbeResponse)
def probe_audience_asymmetry(req: AudienceProbeRequest) -> AudienceProbeResponse:
    """Run counterfactual probe detecting whether report deceptively sugarcoats facts for novice recipients."""
    service = get_causal_deception_service()
    return service.probe_audience(req)
