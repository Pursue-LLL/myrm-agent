"""API endpoints for Multi-Tenant Data Isolation and Cross-Contamination Probes.

[INPUT]
- app.schemas.data_isolation_probes::CompilePartitionKeyRequest, RunIsolationAuditRequest
- app.services.security.data_isolation_probe_service::DataIsolationProbeService

[OUTPUT]
- router: APIRouter for data isolation and cross-contamination probes

[POS]
Security API surface exposing multi-tenant data isolation audit endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from myrm_agent_harness.core.security.data_isolation_probes import (
    TenantMemoryContext,
)

from app.schemas.data_isolation_probes import (
    CompilePartitionKeyRequest,
    CompilePartitionKeyResponse,
    DataSovereigntyReportResponse,
    ProbeScenarioResultSchema,
    RunIsolationAuditRequest,
)
from app.services.security.data_isolation_probe_service import (
    DataIsolationProbeService,
    get_data_isolation_probe_service,
)

router = APIRouter(
    prefix="/isolation-probes",
    tags=["Data Isolation & Cross-Contamination Probes"],
)


@router.post(
    "/compile-partition",
    response_model=CompilePartitionKeyResponse,
    summary="Compile immutable physical partition key for tenant memory",
)
def compile_partition_key_endpoint(
    payload: CompilePartitionKeyRequest,
    service: DataIsolationProbeService = Depends(
        get_data_isolation_probe_service
    ),
) -> CompilePartitionKeyResponse:
    """Compile tamper-evident composite partition key from context."""
    ctx = TenantMemoryContext(
        user_id=payload.context.user_id,
        agent_id=payload.context.agent_id,
        session_id=payload.context.session_id,
        scope=payload.context.scope,
    )
    spec = service.compile_partition_key(ctx)
    return CompilePartitionKeyResponse(
        composite_key=spec.composite_key,
        user_id=spec.user_id,
        agent_id=spec.agent_id,
        scope=spec.scope,
        namespace_digest=spec.namespace_digest,
    )


@router.post(
    "/run-audit",
    response_model=DataSovereigntyReportResponse,
    summary="Run synthetic cross-tenant adversarial isolation audit",
)
def run_isolation_audit_endpoint(
    payload: RunIsolationAuditRequest,
    service: DataIsolationProbeService = Depends(
        get_data_isolation_probe_service
    ),
) -> DataSovereigntyReportResponse:
    """Execute Sybil invariant probes and generate Data Sovereignty Report."""
    ctx = TenantMemoryContext(
        user_id=payload.context.user_id,
        agent_id=payload.context.agent_id,
        session_id=payload.context.session_id,
        scope=payload.context.scope,
    )
    report = service.run_isolation_audit(
        context=ctx,
        environment_type=payload.environment_type,
    )
    scenario_schemas = [
        ProbeScenarioResultSchema(
            scenario=sc.scenario,
            probe_query=sc.probe_query,
            expected_matches=sc.expected_matches,
            actual_matches=sc.actual_matches,
            cross_hits=sc.cross_hits,
            is_isolated=sc.is_isolated,
            details=sc.details,
        )
        for sc in report.scenario_results
    ]
    return DataSovereigntyReportResponse(
        environment_type=report.environment_type,
        total_probes_run=report.total_probes_run,
        cross_hits_count=report.cross_hits_count,
        isolation_pass_rate=report.isolation_pass_rate,
        is_safe=report.is_safe,
        partition_integrity_verified=report.partition_integrity_verified,
        scenario_results=scenario_schemas,
        summary=report.summary,
    )
