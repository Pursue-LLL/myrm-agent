"""API endpoints for Agentic Transaction Safety Pillars and Tri-Flow Isolation.

[INPUT]
- app.schemas.tri_flow_safety::EndpointValidationRequest, ToolCallVerificationRequest
- app.services.security.tri_flow_safety_service::TriFlowSafetyService

[OUTPUT]
- router: APIRouter for transaction safety and tri-flow isolation

[POS]
Security API surface exposing tri-flow isolation and transaction safety endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from myrm_agent_harness.core.security.tri_flow_isolation import (
    DocumentedEndpointSpec,
    ToolRoleContract,
)

from app.schemas.tri_flow_safety import (
    EndpointValidationRequest,
    EndpointValidationResponse,
    RegisterEndpointSpecRequest,
    RegisterToolContractRequest,
    SanitizeLogsRequest,
    SanitizeLogsResponse,
    ToolCallVerificationRequest,
    ToolCallVerificationResponse,
)
from app.services.security.tri_flow_safety_service import (
    TriFlowSafetyService,
    get_tri_flow_safety_service,
)

router = APIRouter(
    prefix="/tri-flow", tags=["Tri-Flow Safety & Transaction Pillars"]
)


@router.post(
    "/verify-call",
    response_model=ToolCallVerificationResponse,
    summary="Verify if tool invocation conforms to active workflow role",
)
def verify_workflow_tool_call(
    payload: ToolCallVerificationRequest,
    service: TriFlowSafetyService = Depends(get_tri_flow_safety_service),
) -> ToolCallVerificationResponse:
    """Validate tool execution against Read-Only, Buyer, and Seller workflow boundaries."""
    result = service.validate_tool_call(
        role=payload.role,
        tool_name=payload.tool_name,
        amount=payload.amount,
        hitl_confirmed=payload.hitl_confirmed,
    )
    return ToolCallVerificationResponse(
        is_allowed=result.is_allowed,
        current_role=result.current_role,
        tool_name=result.tool_name,
        reason=result.reason,
        requires_hitl=result.requires_hitl,
    )


@router.post(
    "/validate-endpoint",
    response_model=EndpointValidationResponse,
    summary="Validate outgoing API or contract method against documented whitelist",
)
def validate_outgoing_endpoint(
    payload: EndpointValidationRequest,
    service: TriFlowSafetyService = Depends(get_tri_flow_safety_service),
) -> EndpointValidationResponse:
    """Enforce Zero-Guesswork guard to block blind probes and undocumented calls."""
    result = service.validate_endpoint_call(
        service=payload.service,
        path=payload.path,
        method=payload.method,
        function_name=payload.function_name,
    )
    return EndpointValidationResponse(
        is_allowed=result.is_allowed,
        service=result.service,
        endpoint=result.endpoint,
        method=result.method,
        reason=result.reason,
    )


@router.post(
    "/sanitize-logs",
    response_model=SanitizeLogsResponse,
    summary="Scrub private keys and sensitive credentials from logs and prompt text",
)
def sanitize_sensitive_logs(
    payload: SanitizeLogsRequest,
    service: TriFlowSafetyService = Depends(get_tri_flow_safety_service),
) -> SanitizeLogsResponse:
    """Zero-print credential scrubber to prevent private keys leaking into stdout."""
    res = service.sanitize_text(payload.raw_text)
    return SanitizeLogsResponse(
        sanitized_text=res.sanitized_text,
        redactions_count=res.redactions_count,
        detected_types=list(res.detected_types),
    )


@router.post(
    "/register-tool",
    response_model=dict[str, str],
    summary="Register tool role and financial constraints",
)
def register_tool_contract(
    payload: RegisterToolContractRequest,
    service: TriFlowSafetyService = Depends(get_tri_flow_safety_service),
) -> dict[str, str]:
    """Register custom tool contract declaring allowed workflow roles."""
    contract = ToolRoleContract(
        tool_name=payload.tool_name,
        allowed_roles=tuple(payload.allowed_roles),
        is_financial_transaction=payload.is_financial_transaction,
        requires_hitl_confirmation=payload.requires_hitl_confirmation,
        financial_threshold=payload.financial_threshold,
    )
    service.register_tool_contract(contract)
    return {
        "status": "registered",
        "tool_name": payload.tool_name,
    }


@router.post(
    "/register-endpoint",
    response_model=dict[str, str],
    summary="Register documented endpoint specification",
)
def register_endpoint_specification(
    payload: RegisterEndpointSpecRequest,
    service: TriFlowSafetyService = Depends(get_tri_flow_safety_service),
) -> dict[str, str]:
    """Register documented endpoint spec to satisfy Zero-Guesswork whitelist."""
    spec = DocumentedEndpointSpec(
        service=payload.service,
        path=payload.path,
        allowed_methods=tuple(payload.allowed_methods),
        contract_functions=tuple(payload.contract_functions),
    )
    service.register_endpoint_spec(spec)
    return {
        "status": "registered",
        "service": payload.service,
        "path": payload.path,
    }
