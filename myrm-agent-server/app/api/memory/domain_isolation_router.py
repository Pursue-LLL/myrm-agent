"""FastAPI router for Connection & Account Domain Isolation (Item 156).

[INPUT]
- HTTP requests for connector-domain mappings, granular grants, and cross-domain egress evaluation.

[OUTPUT]
- JSON responses with ConnectorDomainBindingDTO, DomainGrantConfigDTO, and EgressDecisionDTO.

[POS]
- FastAPI endpoints for Item 156 ConnectionAndAccountDomainIsolation.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.domain_isolation import (
    ConnectorDomainBindingDTO,
    DataDomainDTO,
    DomainGrantConfigDTO,
    EgressDecisionDTO,
    EvaluateEgressRequestDTO,
    SetConnectorDomainRequest,
    UpdateDomainGrantRequest,
    ValidateRecallRequestDTO,
    ValidateRecallResponseDTO,
    ValidateWriteRequestDTO,
    ValidateWriteResponseDTO,
)
from app.services.memory.domain_isolation_service import DomainIsolationService

router = APIRouter(prefix="/domain-isolation", tags=["memory-domain-isolation"])
_service = DomainIsolationService()


def get_domain_isolation_service() -> DomainIsolationService:
    """Dependency helper providing the active DomainIsolationService."""
    return _service


@router.get("/bindings", response_model=list[ConnectorDomainBindingDTO])
async def list_bindings(
    domain: DataDomainDTO | None = Query(default=None, description="Optional domain filter"),
) -> list[ConnectorDomainBindingDTO]:
    """List connector domain bindings."""
    return get_domain_isolation_service().list_bindings(domain=domain)


@router.post(
    "/bindings",
    response_model=ConnectorDomainBindingDTO,
    status_code=status.HTTP_201_CREATED,
)
async def set_binding(req: SetConnectorDomainRequest) -> ConnectorDomainBindingDTO:
    """Declare or update a connector's domain affiliation."""
    return get_domain_isolation_service().set_binding(req)


@router.get("/bindings/{connector_id}", response_model=ConnectorDomainBindingDTO)
async def get_binding(connector_id: str) -> ConnectorDomainBindingDTO:
    """Get domain binding for a specific connector."""
    b = get_domain_isolation_service().get_binding(connector_id)
    if b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector binding {connector_id} not found",
        )
    return b


@router.delete("/bindings/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_binding(connector_id: str) -> None:
    """Remove domain binding for a connector."""
    deleted = get_domain_isolation_service().remove_binding(connector_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector binding {connector_id} not found",
        )


@router.get("/grants", response_model=list[DomainGrantConfigDTO])
async def list_grants() -> list[DomainGrantConfigDTO]:
    """List permissions and security gates for all domains."""
    return get_domain_isolation_service().list_grants()


@router.get("/grants/{domain}", response_model=DomainGrantConfigDTO)
async def get_grant(domain: DataDomainDTO) -> DomainGrantConfigDTO:
    """Get grant configuration for a specific domain."""
    return get_domain_isolation_service().get_grant(domain)


@router.put("/grants/{domain}", response_model=DomainGrantConfigDTO)
async def update_grant(
    domain: DataDomainDTO, req: UpdateDomainGrantRequest
) -> DomainGrantConfigDTO:
    """Update permissions and gates for a specific domain."""
    return get_domain_isolation_service().update_grant(domain, req)


@router.post("/validate-recall", response_model=ValidateRecallResponseDTO)
async def validate_recall(
    req: ValidateRecallRequestDTO,
) -> ValidateRecallResponseDTO:
    """Verify whether memory recall crosses domain isolation boundaries."""
    return get_domain_isolation_service().validate_recall(req)


@router.post("/validate-write", response_model=ValidateWriteResponseDTO)
async def validate_write(
    req: ValidateWriteRequestDTO,
) -> ValidateWriteResponseDTO:
    """Verify whether memory writes are permitted in the target domain."""
    return get_domain_isolation_service().validate_write(req)


@router.post("/evaluate-egress", response_model=EgressDecisionDTO)
async def evaluate_egress(
    req: EvaluateEgressRequestDTO,
) -> EgressDecisionDTO:
    """Evaluate outbound channel egress privacy redlines."""
    return get_domain_isolation_service().evaluate_egress(req)
