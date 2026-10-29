"""System API routes (lazy router re-exports).

[INPUT]
- importlib (POS: 按需导入系统 API 路由模块)
- app.api.system.* (POS: 系统 API 路由模块)

[OUTPUT]
- router: 系统 API 主路由
- __getattr__: 按需暴露各系统 API 路由（缺失依赖时只影响该子路由）

[POS]
系统 API 下挂大量可选观测/计量路由，其中部分依赖尚未就位的 harness 模块。
这里改为惰性再导出：只有真正访问某个子路由时才导入，缺失依赖不会拖垮整个 server。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .router import router

_ROUTER_MODULES: dict[str, str] = {
    "ambient_auxiliary_router": "ambient_auxiliary_accounting_api",
    "event_causality_lineage_router": "event_causality_lineage_api",
    "sandbox_hardware_telemetry_router": "sandbox_hardware_telemetry_api",
    "context_breakdown_router": "context_breakdown_api",
    "coordination_friction_router": "coordination_friction_api",
    "composite_usage_ledger_router": "composite_usage_ledger_api",
    "cron_doctor_router": "cron_doctor_api",
    "custom_agent_insights_router": "custom_agent_insights_api",
    "debug_share_router": "debug_share_api",
    "delivery_dossier_router": "delivery_dossier_api",
    "diagnostic_stream_router": "diagnostic_stream_api",
    "enterprise_credit_cockpit_router": "enterprise_credit_cockpit_api",
    "evidence_cross_verification_router": "evidence_cross_verification_api",
    "failure_triage_router": "failure_triage_api",
    "issue_ticketing_router": "issue_ticketing_api",
    "knowledge_compounding_router": "knowledge_compounding_api",
    "model_ping_router": "model_ping_api",
    "multi_tier_health_router": "multi_tier_health_api",
    "org_spend_limit_router": "org_spend_limit_api",
    "rate_limit_governor_router": "rate_limit_governor_api",
    "rate_limit_split_router": "rate_limit_split_api",
    "resource_ledger_router": "resource_ledger_api",
    "retrieval_trace_router": "retrieval_trace_api",
    "roi_analytics_router": "roi_analytics_api",
    "stream_metrics_router": "stream_metrics_api",
    "token_economics_router": "token_economics_api",
    "turn_context_provenance_router": "turn_context_provenance_api",
    "unattended_reliability_router": "unattended_reliability_api",
    "delegation_billing_router": "delegation_billing_api",
    "aborted_usage_ledger_router": "aborted_usage_ledger_api",
    "active_skill_telemetry_router": "active_skill_telemetry_api",
    "durable_budget_ledger_router": "durable_budget_ledger_api",
    "workflow_burn_router": "workflow_burn_api",
    "unattended_coverage_router": "unattended_coverage_api",
}


def __getattr__(name: str) -> Any:
    """Import a system router on first access."""
    module_name = _ROUTER_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, "router", None)
    if value is None:
        raise AttributeError(f"{module_name} exposes no router")
    globals()[name] = value
    return value


__all__ = [
    "router",
    "ambient_auxiliary_router",
    "event_causality_lineage_router",
    "sandbox_hardware_telemetry_router",
    "context_breakdown_router",
    "coordination_friction_router",
    "composite_usage_ledger_router",
    "cron_doctor_router",
    "custom_agent_insights_router",
    "debug_share_router",
    "delivery_dossier_router",
    "diagnostic_stream_router",
    "enterprise_credit_cockpit_router",
    "evidence_cross_verification_router",
    "failure_triage_router",
    "issue_ticketing_router",
    "knowledge_compounding_router",
    "model_ping_router",
    "multi_tier_health_router",
    "org_spend_limit_router",
    "rate_limit_governor_router",
    "rate_limit_split_router",
    "resource_ledger_router",
    "retrieval_trace_router",
    "roi_analytics_router",
    "stream_metrics_router",
    "token_economics_router",
    "turn_context_provenance_router",
    "unattended_reliability_router",
    "delegation_billing_router",
    "aborted_usage_ledger_router",
    "active_skill_telemetry_router",
    "durable_budget_ledger_router",
    "workflow_burn_router",
    "unattended_coverage_router",
]
