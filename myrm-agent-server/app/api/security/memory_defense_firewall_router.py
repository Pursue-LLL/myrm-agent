"""FastAPI router for Memory Defense Ingestion Firewall and PII Sanitization Suite.

[INPUT]
- app.schemas.memory_defense_firewall::DefenseInspectRequest, ExemptionAddRequest
- app.services.security.memory_defense_firewall_service::MemoryDefenseFirewallService

[OUTPUT]
- router: APIRouter for memory defense firewall endpoints

[POS]
Security API surface exposing memory ingestion firewall and sanitization endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.memory_defense_firewall import (
    DefenseInspectRequest,
    DefenseInspectResponse,
    ExemptionAddRequest,
    ExemptionListResponse,
    ExemptionResponse,
    PatternCatalogResponse,
)
from app.services.security.memory_defense_firewall_service import (
    MemoryDefenseFirewallService,
    get_memory_defense_firewall_service,
)

router = APIRouter(prefix="/security/memory-defense", tags=["Security - Memory Defense Firewall"])


@router.post("/inspect", response_model=DefenseInspectResponse)
async def inspect_memory_content(
    payload: DefenseInspectRequest,
    service: MemoryDefenseFirewallService = Depends(get_memory_defense_firewall_service),
) -> DefenseInspectResponse:
    """Inspect inbound memory text candidate and enforce tri-state ALLOW/REDACT/BLOCK defense."""
    return service.inspect_and_defend(payload)


@router.post("/exemptions", response_model=ExemptionResponse)
async def add_exemption(
    payload: ExemptionAddRequest,
    service: MemoryDefenseFirewallService = Depends(get_memory_defense_firewall_service),
) -> ExemptionResponse:
    """Add a sensitive token or content fingerprint to the false-positive exemption whitelist."""
    return service.add_exemption(payload.token_or_content)


@router.delete("/exemptions", response_model=ExemptionResponse)
async def remove_exemption(
    token_or_content: str = Query(..., description="Token or fingerprint to remove"),
    service: MemoryDefenseFirewallService = Depends(get_memory_defense_firewall_service),
) -> ExemptionResponse:
    """Remove an entry from the false-positive exemption whitelist."""
    return service.remove_exemption(token_or_content)


@router.get("/exemptions", response_model=ExemptionListResponse)
async def list_exemptions(
    service: MemoryDefenseFirewallService = Depends(get_memory_defense_firewall_service),
) -> ExemptionListResponse:
    """List all active false-positive whitelist exemption tokens and fingerprints."""
    return service.list_exemptions()


@router.get("/catalog", response_model=PatternCatalogResponse)
async def get_pattern_catalog(
    service: MemoryDefenseFirewallService = Depends(get_memory_defense_firewall_service),
) -> PatternCatalogResponse:
    """Retrieve the full catalog of 45 built-in sensitive detection pattern specifications."""
    return service.get_pattern_catalog()


@router.get("/audit-records", response_model=list[DefenseInspectResponse])
async def get_audit_records(
    limit: int = Query(default=50, ge=1, le=500),
    service: MemoryDefenseFirewallService = Depends(get_memory_defense_firewall_service),
) -> list[DefenseInspectResponse]:
    """Retrieve historical audit records of memory defense evaluations and redactions."""
    return service.get_audit_records(limit=limit)
