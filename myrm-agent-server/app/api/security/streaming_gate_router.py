"""API router for Streaming Endpoint Identity Gate Parity.

[INPUT]
- EvaluateStreamingAccessRequest, StreamingEndpointContractDto.

[OUTPUT]
- Endpoints for querying streaming route contracts, evaluating client access gates,
  and executing security parity audits across event streams.

[POS]
- Server API. Mounted under /api/v1/security/streaming-gate.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.schemas.streaming_gate import (
    EvaluateStreamingAccessRequest,
    EvaluateStreamingAccessResponse,
    StreamingEndpointContractDto,
    StreamingParityAuditResponse,
)
from app.services.security.streaming_gate_service import (
    get_streaming_gate_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/streaming-gate", tags=["streaming-gate"])


@router.get("/contracts", response_model=list[StreamingEndpointContractDto])
def list_streaming_contracts() -> list[StreamingEndpointContractDto]:
    """Retrieve all declared streaming endpoint security contracts."""
    service = get_streaming_gate_service()
    return service.list_contracts()


@router.post(
    "/contracts",
    response_model=StreamingEndpointContractDto,
    status_code=status.HTTP_201_CREATED,
)
def register_streaming_contract(
    contract: StreamingEndpointContractDto,
) -> StreamingEndpointContractDto:
    """Register or update a streaming route security gate contract."""
    service = get_streaming_gate_service()
    service.register_contract(contract)
    return contract


@router.post("/evaluate", response_model=EvaluateStreamingAccessResponse)
def evaluate_streaming_access(
    req: EvaluateStreamingAccessRequest,
) -> EvaluateStreamingAccessResponse:
    """Evaluate whether client identity has permission to subscribe to a streaming route."""
    service = get_streaming_gate_service()
    return service.evaluate_access(req)


@router.get("/audit", response_model=StreamingParityAuditResponse)
def run_streaming_parity_audit() -> StreamingParityAuditResponse:
    """Audit all declared streaming routes to detect identity gate or scope parity defects."""
    service = get_streaming_gate_service()
    return service.run_parity_audit()
