"""Security sub-router registration assembly.

Aggregates all modular security domain routers and registers them to the root security router.
Maintains clean architectural boundaries and prevents single-file length inflation.

[POS] app/api/security/sub_routers.py
[INPUT] app.api.security.*
[OUTPUT] register_security_sub_routers
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.security.action_grant_router import router as action_grant_router
from app.api.security.admin_auth_surface_router import router as admin_auth_surface_router
from app.api.security.air_gapped_router import router as air_gapped_router
from app.api.security.approval_metrics_router import router as approval_metrics_router
from app.api.security.asr_privacy_tradeoff_router import router as asr_privacy_tradeoff_router
from app.api.security.attestation_router import router as attestation_router
from app.api.security.audit_coverage_router import router as audit_coverage_router
from app.api.security.bot_budget_guardrail_router import router as bot_budget_guardrail_router
from app.api.security.causal_deception_router import router as causal_deception_router
from app.api.security.change_guard_router import router as change_guard_router
from app.api.security.client_secret_router import router as client_secret_router
from app.api.security.commerce_dispute_escrow_router import (
    router as commerce_dispute_escrow_router,
)
from app.api.security.companion_relationship_guard_router import (
    router as companion_relationship_guard_router,
)
from app.api.security.compound_shell_risk_router import router as compound_shell_risk_router
from app.api.security.connector_guard_router import router as connector_guard_router
from app.api.security.connector_trust_router import router as connector_trust_router
from app.api.security.credential_shield_router import router as credential_shield_router
from app.api.security.data_erasure_portability_router import (
    router as data_erasure_portability_router,
)
from app.api.security.data_isolation_probe_router import router as data_isolation_probe_router
from app.api.security.data_plane_defense_router import router as data_plane_defense_router
from app.api.security.desktop_enclave_router import router as desktop_enclave_router
from app.api.security.desktop_micro_isolation_router import (
    router as desktop_micro_isolation_router,
)
from app.api.security.desktop_oauth_device_router import router as desktop_oauth_device_router
from app.api.security.dev_sandbox_fence_router import router as dev_sandbox_fence_router
from app.api.security.dir_trust_gate_router import router as dir_trust_gate_router
from app.api.security.directory_trust_gate_router import router as directory_trust_gate_router
from app.api.security.directory_trust_remote_memory_router import (
    router as directory_trust_remote_memory_router,
)
from app.api.security.docker_sandbox_hardening_router import (
    router as docker_sandbox_hardening_router,
)
from app.api.security.dual_tier_isolation_router import router as dual_tier_isolation_router
from app.api.security.dual_track_sandbox_guard_router import (
    router as dual_track_sandbox_guard_router,
)
from app.api.security.egress_dlp_router import router as egress_dlp_router
from app.api.security.executable_probe_router import router as executable_probe_router
from app.api.security.externally_visible_action_router import (
    router as externally_visible_action_router,
)
from app.api.security.financial_boundary_router import router as financial_boundary_router
from app.api.security.financial_safety_guard_router import (
    router as financial_safety_guard_router,
)
from app.api.security.gate_guard_sanitizer_router import router as gate_guard_sanitizer_router
from app.api.security.git_leak_shield_router import router as git_leak_shield_router
from app.api.security.governance_assembly_router import router as governance_assembly_router
from app.api.security.hitl_denial_events_router import router as hitl_denial_events_router
from app.api.security.hitl_denial_router import router as hitl_denial_router
from app.api.security.hitl_fail_closed_router import router as hitl_fail_closed_router
from app.api.security.inbound_quarantine_router import router as inbound_quarantine_router
from app.api.security.inherited_identity_guard_router import (
    router as inherited_identity_guard_router,
)
from app.api.security.integration_trust_router import router as integration_trust_router
from app.api.security.ipc_router import router as ipc_router
from app.api.security.irreversible_write_guard_router import (
    router as irreversible_write_guard_router,
)
from app.api.security.license_compliance_router import router as license_compliance_router
from app.api.security.llm_egress_guard_router import router as llm_egress_guard_router
from app.api.security.local_first_vault_router import router as local_first_vault_router
from app.api.security.localhost_anti_hijack_router import router as localhost_anti_hijack_router
from app.api.security.marketplace_contract_router import router as marketplace_contract_router
from app.api.security.memory_defense_firewall_router import (
    router as memory_defense_firewall_router,
)
from app.api.security.muse_sentinel_isolation_router import (
    router as muse_sentinel_isolation_router,
)
from app.api.security.native_credential_approval_router import (
    router as native_credential_approval_router,
)
from app.api.security.on_demand_masking_router import router as on_demand_masking_router
from app.api.security.pii_vault_router import router as pii_vault_router
from app.api.security.plugin_guardrail_router import router as plugin_guardrail_router
from app.api.security.plugin_trust_attestation_router import (
    router as plugin_trust_attestation_router,
)
from app.api.security.policy_snapshot_router import router as policy_snapshot_router
from app.api.security.pre_flight_budget_router import router as pre_flight_budget_router
from app.api.security.pre_tool_use_interceptor_router import (
    router as pre_tool_use_interceptor_router,
)
from app.api.security.prompt_anti_extraction_router import (
    router as prompt_anti_extraction_router,
)
from app.api.security.provenance_staging_router import router as provenance_staging_router
from app.api.security.risk_evaluator_router import router as risk_evaluator_router
from app.api.security.saga_dual_engine_router import router as saga_dual_engine_router
from app.api.security.sandbox_log_continuation_router import (
    router as sandbox_log_continuation_router,
)
from app.api.security.sandbox_trust_audit_router import router as sandbox_trust_audit_router
from app.api.security.scoped_css_sentinel_router import router as scoped_css_sentinel_router
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
from app.api.security.slack_rotating_token_router import router as slack_rotating_token_router
from app.api.security.sso_redirect_idempotent_router import (
    router as sso_redirect_idempotent_router,
)
from app.api.security.sso_redirect_router import router as sso_redirect_router
from app.api.security.stacked_policy_governance_router import (
    router as stacked_policy_governance_router,
)
from app.api.security.streaming_gate_router import router as streaming_gate_router
from app.api.security.structured_scan_errors_router import (
    router as structured_scan_errors_router,
)
from app.api.security.tracing_redaction_router import router as tracing_redaction_router
from app.api.security.tri_flow_safety_router import router as tri_flow_safety_router
from app.api.security.tripartite_ledger_router import router as tripartite_ledger_router
from app.api.security.untrusted_config_guard_router import (
    router as untrusted_config_guard_router,
)
from app.api.security.webhook_guard_router import router as webhook_guard_router
from app.api.security.workspace_boundary_router import router as workspace_boundary_router
from app.api.security.workspace_path_rbac_router import router as workspace_path_rbac_router
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

_SECURITY_SUBROUTERS: tuple[APIRouter, ...] = (
    attestation_router,
    client_secret_router,
    ipc_router,
    git_leak_shield_router,
    desktop_enclave_router,
    risk_evaluator_router,
    provenance_staging_router,
    data_plane_defense_router,
    pii_vault_router,
    air_gapped_router,
    secret_broker_router,
    secops_audit_router,
    workspace_scoper_router,
    webhook_guard_router,
    financial_boundary_router,
    skill_governance_router,
    skill_spector_scanner_router,
    tripartite_ledger_router,
    governance_assembly_router,
    policy_snapshot_router,
    semantic_rbac_router,
    saga_dual_engine_router,
    desktop_micro_isolation_router,
    causal_deception_router,
    audit_coverage_router,
    streaming_gate_router,
    marketplace_contract_router,
    integration_trust_router,
    license_compliance_router,
    workspace_boundary_router,
    egress_dlp_router,
    zero_egress_provenance_router,
    credential_shield_router,
    hitl_fail_closed_router,
    hitl_denial_events_router,
    desktop_oauth_device_router,
    dual_tier_isolation_router,
    dual_track_sandbox_guard_router,
    structured_scan_errors_router,
    llm_egress_guard_router,
    sandbox_log_continuation_router,
    directory_trust_remote_memory_router,
    directory_trust_gate_router,
    approval_metrics_router,
    companion_relationship_guard_router,
    gate_guard_sanitizer_router,
    change_guard_router,
    native_credential_approval_router,
    inherited_identity_guard_router,
    slack_rotating_token_router,
    sso_redirect_router,
    hitl_denial_router,
    sso_redirect_idempotent_router,
    tracing_redaction_router,
    executable_probe_router,
    dir_trust_gate_router,
    admin_auth_surface_router,
    on_demand_masking_router,
    asr_privacy_tradeoff_router,
    commerce_dispute_escrow_router,
    inbound_quarantine_router,
    workspace_path_rbac_router,
    pre_tool_use_interceptor_router,
    pre_flight_budget_router,
    docker_sandbox_hardening_router,
    zero_credential_proxy_router,
    compound_shell_risk_router,
    connector_guard_router,
    untrusted_config_guard_router,
    dev_sandbox_fence_router,
    sensitive_file_guard_router,
    irreversible_write_guard_router,
    muse_sentinel_isolation_router,
    sandbox_trust_audit_router,
    local_first_vault_router,
    scoped_css_sentinel_router,
    localhost_anti_hijack_router,
    action_grant_router,
    tri_flow_safety_router,
    data_isolation_probe_router,
    stacked_policy_governance_router,
    secretless_egress_proxy_router,
    memory_defense_firewall_router,
    financial_safety_guard_router,
    connector_trust_router,
    plugin_guardrail_router,
    externally_visible_action_router,
    bot_budget_guardrail_router,
    zero_defense_reverification_router,
    prompt_anti_extraction_router,
    plugin_trust_attestation_router,
    data_erasure_portability_router,
)


def register_security_subrouters(parent_router: APIRouter) -> None:
    """Register all modular security sub-routers onto the parent security router."""
    for sub in _SECURITY_SUBROUTERS:
        parent_router.include_router(sub)
