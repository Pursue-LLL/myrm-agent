"""
Security Dashboard API

Aggregates GitHub Security API and control-plane webhook-backed alerts.
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.api.security.action_grant_router import (
    router as action_grant_router,
)
from app.api.security.admin_auth_surface_router import (
    router as admin_auth_surface_router,
)
from app.api.security.air_gapped_router import router as air_gapped_router
from app.api.security.approval_metrics_router import (
    router as approval_metrics_router,
)
from app.api.security.asr_privacy_tradeoff_router import (
    router as asr_privacy_tradeoff_router,
)
from app.api.security.attestation_router import router as attestation_router
from app.api.security.audit_coverage_router import (
    router as audit_coverage_router,
)
from app.api.security.bot_budget_guardrail_router import (
    router as bot_budget_guardrail_router,
)
from app.api.security.causal_deception_router import (
    router as causal_deception_router,
)
from app.api.security.change_guard_router import (
    router as change_guard_router,
)
from app.api.security.client_secret_router import router as client_secret_router
from app.api.security.commerce_dispute_escrow_router import (
    router as commerce_dispute_escrow_router,
)
from app.api.security.companion_relationship_guard_router import (
    router as companion_relationship_guard_router,
)
from app.api.security.compound_shell_risk_router import (
    router as compound_shell_risk_router,
)
from app.api.security.connector_guard_router import (
    router as connector_guard_router,
)
from app.api.security.connector_trust_router import (
    router as connector_trust_router,
)
from app.api.security.credential_shield_router import (
    router as credential_shield_router,
)
from app.api.security.data_isolation_probe_router import (
    router as data_isolation_probe_router,
)
from app.api.security.data_plane_defense_router import (
    router as data_plane_defense_router,
)
from app.api.security.desktop_enclave_router import router as desktop_enclave_router
from app.api.security.desktop_micro_isolation_router import (
    router as desktop_micro_isolation_router,
)
from app.api.security.desktop_oauth_device_router import (
    router as desktop_oauth_device_router,
)
from app.api.security.dev_sandbox_fence_router import (
    router as dev_sandbox_fence_router,
)
from app.api.security.dir_trust_gate_router import (
    router as dir_trust_gate_router,
)
from app.api.security.directory_trust_gate_router import (
    router as directory_trust_gate_router,
)
from app.api.security.directory_trust_remote_memory_router import (
    router as directory_trust_remote_memory_router,
)
from app.api.security.docker_sandbox_hardening_router import (
    router as docker_sandbox_hardening_router,
)
from app.api.security.dual_tier_isolation_router import (
    router as dual_tier_isolation_router,
)
from app.api.security.dual_track_sandbox_guard_router import (
    router as dual_track_sandbox_guard_router,
)
from app.api.security.egress_dlp_router import router as egress_dlp_router
from app.api.security.executable_probe_router import (
    router as executable_probe_router,
)
from app.api.security.externally_visible_action_router import (
    router as externally_visible_action_router,
)
from app.api.security.financial_boundary_router import (
    router as financial_boundary_router,
)
from app.api.security.financial_safety_guard_router import (
    router as financial_safety_guard_router,
)
from app.api.security.gate_guard_sanitizer_router import (
    router as gate_guard_sanitizer_router,
)
from app.api.security.git_leak_shield_router import router as git_leak_shield_router
from app.api.security.governance_assembly_router import (
    router as governance_assembly_router,
)
from app.api.security.hitl_denial_events_router import (
    router as hitl_denial_events_router,
)
from app.api.security.hitl_denial_router import (
    router as hitl_denial_router,
)
from app.api.security.hitl_fail_closed_router import (
    router as hitl_fail_closed_router,
)
from app.api.security.inbound_quarantine_router import (
    router as inbound_quarantine_router,
)
from app.api.security.inherited_identity_guard_router import (
    router as inherited_identity_guard_router,
)
from app.api.security.integration_trust_router import (
    router as integration_trust_router,
)
from app.api.security.ipc_router import router as ipc_router
from app.api.security.irreversible_write_guard_router import (
    router as irreversible_write_guard_router,
)
from app.api.security.license_compliance_router import (
    router as license_compliance_router,
)
from app.api.security.llm_egress_guard_router import (
    router as llm_egress_guard_router,
)
from app.api.security.local_first_vault_router import (
    router as local_first_vault_router,
)
from app.api.security.localhost_anti_hijack_router import (
    router as localhost_anti_hijack_router,
)
from app.api.security.marketplace_contract_router import (
    router as marketplace_contract_router,
)
from app.api.security.memory_defense_firewall_router import (
    router as memory_defense_firewall_router,
)
from app.api.security.muse_sentinel_isolation_router import (
    router as muse_sentinel_isolation_router,
)
from app.api.security.native_credential_approval_router import (
    router as native_credential_approval_router,
)
from app.api.security.on_demand_masking_router import (
    router as on_demand_masking_router,
)
from app.api.security.pii_vault_router import router as pii_vault_router
from app.api.security.plugin_guardrail_router import (
    router as plugin_guardrail_router,
)
from app.api.security.policy_snapshot_router import router as policy_snapshot_router
from app.api.security.pre_flight_budget_router import (
    router as pre_flight_budget_router,
)
from app.api.security.pre_tool_use_interceptor_router import (
    router as pre_tool_use_interceptor_router,
)
from app.api.security.provenance_staging_router import (
    router as provenance_staging_router,
)
from app.api.security.risk_evaluator_router import router as risk_evaluator_router
from app.api.security.saga_dual_engine_router import router as saga_dual_engine_router
from app.api.security.sandbox_log_continuation_router import (
    router as sandbox_log_continuation_router,
)
from app.api.security.sandbox_trust_audit_router import (
    router as sandbox_trust_audit_router,
)
from app.api.security.scoped_css_sentinel_router import (
    router as scoped_css_sentinel_router,
)
from app.api.security.secops_audit_router import router as secops_audit_router
from app.api.security.secret_broker_router import router as secret_broker_router
from app.api.security.secretless_egress_proxy_router import (
    router as secretless_egress_proxy_router,
)
from app.api.security.semantic_rbac_router import router as semantic_rbac_router
from app.api.security.sensitive_file_guard_router import (
    router as sensitive_file_guard_router,
)
from app.api.security.skill_governance_router import router as skill_governance_router
from app.api.security.skill_spector_scanner_router import (
    router as skill_spector_scanner_router,
)
from app.api.security.slack_rotating_token_router import (
    router as slack_rotating_token_router,
)
from app.api.security.sso_redirect_idempotent_router import (
    router as sso_redirect_idempotent_router,
)
from app.api.security.sso_redirect_router import (
    router as sso_redirect_router,
)
from app.api.security.stacked_policy_governance_router import (
    router as stacked_policy_governance_router,
)
from app.api.security.streaming_gate_router import (
    router as streaming_gate_router,
)
from app.api.security.structured_scan_errors_router import (
    router as structured_scan_errors_router,
)
from app.api.security.tracing_redaction_router import (
    router as tracing_redaction_router,
)
from app.api.security.tri_flow_safety_router import (
    router as tri_flow_safety_router,
)
from app.api.security.tripartite_ledger_router import router as tripartite_ledger_router
from app.api.security.untrusted_config_guard_router import (
    router as untrusted_config_guard_router,
)
from app.api.security.webhook_guard_router import router as webhook_guard_router
from app.api.security.workspace_boundary_router import (
    router as workspace_boundary_router,
)
from app.api.security.workspace_path_rbac_router import (
    router as workspace_path_rbac_router,
)
from app.api.security.workspace_scoper_router import router as workspace_scoper_router
from app.api.security.zero_credential_proxy_router import (
    router as zero_credential_proxy_router,
)
from app.api.security.zero_defense_reverification_router import (
    router as zero_defense_reverification_router,
)
from app.api.security.zero_egress_provenance_router import (
    router as zero_egress_provenance_router,
)
from app.config.settings import settings as _settings
from app.schemas.security.dashboard import (
    DependabotPR,
    DualTrackAuditEntryItem,
    DualTrackAuditStatsResponse,
    PlatformAuditLogsResponse,
    PlatformAuditStatsResponse,
    SecurityAlert,
    SecurityDashboard,
    SecurityRateLimitsResponse,
    SecuritySetupHints,
)
from app.services.security.cp_rate_limit import fetch_cp_rate_limits
from app.services.security.dashboard_settings import load_monitored_github_repos
from app.services.security.dual_track_audit import (
    export_dual_track_compliance_dossier,
    fetch_dual_track_audit_entries,
    fetch_dual_track_audit_stats,
)
from app.services.security.github_supplement import fetch_dependabot_prs_for_repo
from app.services.security.merged_dashboard import (
    build_security_dashboard,
    build_setup_hints,
)
from app.services.security.platform_audit import (
    export_platform_audit_logs,
    fetch_platform_audit_logs,
    fetch_platform_audit_stats,
)

logger = logging.getLogger(__name__)

GITHUB_TOKEN = _settings.services.github_token.get_secret_value()
DEFAULT_REPO = "Pursue-LLL/myrm-agent"

router = APIRouter(prefix="/security", tags=["security"])

router.include_router(attestation_router)
router.include_router(client_secret_router)
router.include_router(ipc_router)
router.include_router(git_leak_shield_router)
router.include_router(desktop_enclave_router)
router.include_router(risk_evaluator_router)
router.include_router(provenance_staging_router)
router.include_router(data_plane_defense_router)
router.include_router(pii_vault_router)
router.include_router(air_gapped_router)
router.include_router(secret_broker_router)
router.include_router(secops_audit_router)
router.include_router(workspace_scoper_router)
router.include_router(webhook_guard_router)
router.include_router(financial_boundary_router)
router.include_router(skill_governance_router)
router.include_router(skill_spector_scanner_router)
router.include_router(tripartite_ledger_router)
router.include_router(governance_assembly_router)
router.include_router(policy_snapshot_router)
router.include_router(semantic_rbac_router)
router.include_router(saga_dual_engine_router)
router.include_router(desktop_micro_isolation_router)
router.include_router(causal_deception_router)
router.include_router(audit_coverage_router)
router.include_router(streaming_gate_router)
router.include_router(marketplace_contract_router)
router.include_router(integration_trust_router)
router.include_router(license_compliance_router)
router.include_router(workspace_boundary_router)
router.include_router(egress_dlp_router)
router.include_router(zero_egress_provenance_router)
router.include_router(credential_shield_router)
router.include_router(hitl_fail_closed_router)
router.include_router(hitl_denial_events_router)
router.include_router(desktop_oauth_device_router)
router.include_router(dual_tier_isolation_router)
router.include_router(dual_track_sandbox_guard_router)
router.include_router(structured_scan_errors_router)
router.include_router(llm_egress_guard_router)
router.include_router(sandbox_log_continuation_router)
router.include_router(directory_trust_remote_memory_router)
router.include_router(directory_trust_gate_router)
router.include_router(approval_metrics_router)
router.include_router(companion_relationship_guard_router)
router.include_router(gate_guard_sanitizer_router)
router.include_router(change_guard_router)
router.include_router(native_credential_approval_router)
router.include_router(inherited_identity_guard_router)
router.include_router(slack_rotating_token_router)
router.include_router(sso_redirect_router)
router.include_router(hitl_denial_router)
router.include_router(sso_redirect_idempotent_router)
router.include_router(tracing_redaction_router)
router.include_router(executable_probe_router)
router.include_router(dir_trust_gate_router)
router.include_router(admin_auth_surface_router)
router.include_router(on_demand_masking_router)
router.include_router(asr_privacy_tradeoff_router)
router.include_router(commerce_dispute_escrow_router)
router.include_router(inbound_quarantine_router)
router.include_router(workspace_path_rbac_router)
router.include_router(pre_tool_use_interceptor_router)
router.include_router(pre_flight_budget_router)
router.include_router(docker_sandbox_hardening_router)
router.include_router(zero_credential_proxy_router)
router.include_router(compound_shell_risk_router)
router.include_router(connector_guard_router)
router.include_router(untrusted_config_guard_router)
router.include_router(dev_sandbox_fence_router)
router.include_router(sensitive_file_guard_router)
router.include_router(irreversible_write_guard_router)
router.include_router(muse_sentinel_isolation_router)
router.include_router(sandbox_trust_audit_router)
router.include_router(local_first_vault_router)
router.include_router(scoped_css_sentinel_router)
router.include_router(localhost_anti_hijack_router)
router.include_router(action_grant_router)
router.include_router(tri_flow_safety_router)
router.include_router(data_isolation_probe_router)
router.include_router(stacked_policy_governance_router)
router.include_router(secretless_egress_proxy_router)
router.include_router(memory_defense_firewall_router)
router.include_router(financial_safety_guard_router)
router.include_router(connector_trust_router)
router.include_router(plugin_guardrail_router)
router.include_router(externally_visible_action_router)
router.include_router(bot_budget_guardrail_router)
router.include_router(zero_defense_reverification_router)
router.include_router(skill_spector_scanner_router)


@router.get("/dashboard", response_model=SecurityDashboard)
async def get_security_dashboard() -> SecurityDashboard:
    """Security dashboard: GitHub (local) or CP alerts + GitHub PR/SBOM (sandbox)."""
    return await build_security_dashboard()


@router.get("/setup-hints", response_model=SecuritySetupHints)
async def get_security_setup_hints() -> SecuritySetupHints:
    """Webhook URL and env hints for SaaS (tenant id = platform user id)."""
    return await build_setup_hints()


@router.get("/rate-limits", response_model=SecurityRateLimitsResponse)
async def get_security_rate_limits() -> SecurityRateLimitsResponse:
    """Platform rate limits from control plane (sandbox only)."""
    return await fetch_cp_rate_limits()


@router.get("/alerts", response_model=list[SecurityAlert])
async def get_security_alerts(
    severity: str | None = None,
    state: str | None = "open",
) -> list[SecurityAlert]:
    dashboard = await build_security_dashboard()
    alerts = dashboard.recent_alerts
    if severity:
        alerts = [alert for alert in alerts if alert.severity == severity]
    if state:
        alerts = [alert for alert in alerts if alert.state == state]
    return alerts


@router.get("/audit/logs", response_model=PlatformAuditLogsResponse)
async def get_platform_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
) -> PlatformAuditLogsResponse:
    """Platform audit logs: control plane (sandbox) or local auth JSONL."""
    return await fetch_platform_audit_logs(limit=limit)


@router.get("/audit/stats", response_model=PlatformAuditStatsResponse)
async def get_platform_audit_stats(
    hours: int = Query(24, ge=1, le=168),
) -> PlatformAuditStatsResponse:
    """Aggregated platform audit statistics for the security dashboard."""
    return await fetch_platform_audit_stats(hours=hours)


@router.get("/audit/export")
async def export_platform_audit(
    format: Literal["csv", "json"] = Query("csv"),
) -> Response:
    """Export platform audit logs as CSV or JSON."""
    return await export_platform_audit_logs(export_format=format)


@router.get("/audit/dual-track/entries", response_model=list[DualTrackAuditEntryItem])
async def get_dual_track_audit_entries(
    session_id: str | None = None,
    agent_id: str | None = None,
    outcome: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[DualTrackAuditEntryItem]:
    """Dual-track prior audit entries with fail-closed pre-act and paired post-act status."""
    resolved_limit = limit if isinstance(limit, int) else 100
    return fetch_dual_track_audit_entries(
        session_id=session_id,
        agent_id=agent_id,
        outcome=outcome,
        limit=resolved_limit,
    )


@router.get("/audit/dual-track/stats", response_model=DualTrackAuditStatsResponse)
async def get_dual_track_audit_stats(
    session_id: str | None = None,
    agent_id: str | None = None,
) -> DualTrackAuditStatsResponse:
    """Aggregated compliance metrics, pass rate, and rule trigger rankings."""
    return fetch_dual_track_audit_stats(session_id=session_id, agent_id=agent_id)


@router.get("/audit/dual-track/export")
async def export_dual_track_audit(
    format: Literal["json", "csv", "markdown"] = Query("json"),
    session_id: str | None = None,
    agent_id: str | None = None,
) -> Response:
    """Export sealed zero-leakage compliance audit dossier as JSON, CSV, or Markdown."""
    return export_dual_track_compliance_dossier(
        export_format=format,
        session_id=session_id,
        agent_id=agent_id,
    )


@router.get("/dependabot-prs", response_model=list[DependabotPR])
async def get_dependabot_prs() -> list[DependabotPR]:
    try:
        token = GITHUB_TOKEN.strip() or None
        monitored = await load_monitored_github_repos()
        repo = monitored[0] if monitored else DEFAULT_REPO
        return await fetch_dependabot_prs_for_repo(repo, token)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "GitHub API error (status %s): %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail="GitHub API error",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Failed to fetch Dependabot PRs"
        ) from exc
