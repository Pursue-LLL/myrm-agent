from fastapi import APIRouter

from app.api.a2a.router import router as a2a_router
from app.api.agents import agent as user_agent
from app.api.agents import (
    agent_extras,
    agent_history,
    agent_portability,
    ai_build,
    general_agent,
    generate_prompt,
    providers,
    subagents,
    suggestions,
    templates,
)
from app.api.agents.adaptive_wakeup_router import router as adaptive_wakeup_router
from app.api.agents.advisor_channel_router import router as advisor_channel_router
from app.api.agents.agent_assembler_router import router as agent_assembler_router
from app.api.agents.agent_avatar_router import router as agent_avatar_router
from app.api.agents.agent_handoff_router import router as agent_handoff_router
from app.api.agents.agent_hierarchy_router import router as agent_hierarchy_router
from app.api.agents.agent_multiplexer_router import router as agent_multiplexer_router
from app.api.agents.agent_operations_router import router as agent_operations_router
from app.api.agents.agent_teams_router import router as agent_teams_router
from app.api.agents.autonomous_loop_router import router as autonomous_loop_router
from app.api.agents.bot_forge_router import router as bot_forge_router
from app.api.agents.bot_mode_router import router as bot_mode_router
from app.api.agents.capability_dispatch_router import router as capability_dispatch_router
from app.api.agents.clean_code_pipeline_router import router as clean_code_pipeline_router
from app.api.agents.cli_passthrough_router import router as cli_passthrough_router
from app.api.agents.cloud_edge_relay_router import router as cloud_edge_relay_router
from app.api.agents.coauthoring_ledger_router import router as coauthoring_ledger_router
from app.api.agents.coding_wave_router import router as coding_wave_router
from app.api.agents.conflict_gate_router import router as conflict_gate_router
from app.api.agents.council_router import router as council_router
from app.api.agents.creator_mode_router import router as creator_mode_router
from app.api.agents.cross_surface_bridge_router import router as cross_surface_bridge_router
from app.api.agents.dag_orchestrator_router import router as dag_orchestrator_router
from app.api.agents.debate_synthesis_router import router as debate_synthesis_router
from app.api.agents.debate_workroom_router import router as debate_workroom_router
from app.api.agents.device_mesh_router import router as device_mesh_router
from app.api.agents.diamond_graph_router import router as diamond_graph_router
from app.api.agents.durable_dispatch_router import router as durable_dispatch_router
from app.api.agents.external_agent_bridge_router import router as external_agent_bridge_router
from app.api.agents.external_bundle_router import router as external_bundle_router
from app.api.agents.failure_facts_router import router as failure_facts_router
from app.api.agents.failure_policy_router import router as failure_policy_router
from app.api.agents.fleet_overview import router as fleet_overview_router
from app.api.agents.fleet_telemetry import router as fleet_telemetry_router
from app.api.agents.fusen_router import router as fusen_router
from app.api.agents.governance import router as governance_router
from app.api.agents.infra_quota_router import router as infra_quota_router
from app.api.agents.kanban_dispatcher_router import router as kanban_dispatcher_router
from app.api.agents.kanban_orchestrator_router import router as kanban_orchestrator_router
from app.api.agents.kanban_queue_router import router as kanban_queue_router
from app.api.agents.mcp_payload_summarizer_router import router as mcp_payload_summarizer_router
from app.api.agents.mcp_scope_gate_router import router as mcp_scope_gate_router
from app.api.agents.memory_hub_router import router as memory_hub_router
from app.api.agents.mixed_fleet_router import router as mixed_fleet_router
from app.api.agents.multi_bot_focus_router import router as multi_bot_focus_router
from app.api.agents.multi_lane_router import router as multi_lane_router
from app.api.agents.openapi_services import router as openapi_services_router
from app.api.agents.pipeline_integrity_router import router as pipeline_integrity_router
from app.api.agents.profile_audit import router as profile_audit_router
from app.api.agents.ralph_workflow_router import router as ralph_workflow_router
from app.api.agents.readiness import router as readiness_router
from app.api.agents.recovery import router as agent_recovery_router
from app.api.agents.replay_dedup_router import router as replay_dedup_router
from app.api.agents.report_fifo_router import router as report_fifo_router
from app.api.agents.review_loop_router import router as review_loop_router
from app.api.agents.scope_guardrails_router import router as scope_guardrails_router
from app.api.agents.session_fork_router import router as session_fork_router
from app.api.agents.skill_bundle_router import router as skill_bundle_router
from app.api.agents.socket_mesh_router import router as socket_mesh_router
from app.api.agents.specialist_summoning_router import router as specialist_summoning_router
from app.api.agents.split_session_goal_router import router as split_session_goal_router
from app.api.agents.squad_composition_router import router as squad_composition_router
from app.api.agents.subagent_hub_router import router as subagent_hub_router
from app.api.agents.subagent_lifecycle_router import router as subagent_lifecycle_router
from app.api.agents.subagent_scaling_router import router as subagent_scaling_router
from app.api.agents.swarm_mesh_router import router as swarm_mesh_router
from app.api.agents.swarm_offload_router import router as swarm_offload_router
from app.api.agents.todo_store_router import router as todo_store_router
from app.api.agents.token_budget_governance_router import router as token_budget_governance_router
from app.api.agents.topology_pruning_router import router as topology_pruning_router
from app.api.agents.tri_role_router import router as tri_role_router
from app.api.agents.vertical_presets_router import router as vertical_presets_router
from app.api.agents.virtual_room_router import router as virtual_room_router
from app.api.agents.visual_timeline_router import router as visual_timeline_router
from app.api.agents.workspace_blueprint_router import router as workspace_blueprint_router
from app.api.agents.workspace_inheritance_router import router as workspace_inheritance_router
from app.api.agents.zero_token_contract_router import router as zero_token_contract_router
from app.api.api_keys import router as api_keys_router
from app.api.approvals import router as approvals_router
from app.api.audit.bash_router import router as audit_router
from app.api.background_tasks.router import router as background_tasks_router
from app.api.batch_directory import router as batch_directory_router
from app.api.browser_domain_skills import router as browser_domain_skills_router
from app.api.browser_recording import router as browser_recording_router
from app.api.browser_sessions import router as browser_sessions_router
from app.api.browser_spaces import router as browser_spaces_router
from app.api.budget import budget_router
from app.api.chats import router as chat_router
from app.api.chats.chat.share import public_router as chat_share_public_router
from app.api.chats.group_chat_router import router as group_chat_router
from app.api.chats.session_export_router import router as session_export_router
from app.api.checkpoint import router as checkpoint_router
from app.api.client_logs import router as client_logs_router
from app.api.commerce.spending_router import router as commerce_spending_router
from app.api.companion.doctor_router import router as companion_doctor_router
from app.api.companion.router import router as companion_router
from app.api.compounding_playbook import router as compounding_playbook_router
from app.api.config.artifact_mappings import router as artifact_mappings_router
from app.api.config.model_overrides_router import model_overrides_router
from app.api.config.router import router as config_router
from app.api.connect.router import router as connect_router
from app.api.context.omni_reference import router as omni_reference_router
from app.api.context.router import router as context_bundle_router
from app.api.credentials.router import router as credentials_router
from app.api.cron.routes import router as cron_router
from app.api.datasets import router as datasets_router
from app.api.dev_ports import router as dev_ports_router
from app.api.eval.router import router as eval_router
from app.api.extension import router as extension_router
from app.api.extension import ws_router as extension_ws_router
from app.api.external_agents import router as external_agents_router
from app.api.faq import router as faq_router
from app.api.features.router import router as features_router
from app.api.files.artifact_share_api import (
    public_router as artifact_share_public_router,
)
from app.api.files.router import router as files_router
from app.api.files.vault_proxy import router as vault_proxy_router
from app.api.git import router as git_worktree_router
from app.api.goals.router import router as goals_router
from app.api.health.router import router as health_router
from app.api.instance_archive.router import router as instance_archive_router
from app.api.integrations import router as integrations_router
from app.api.kanban.pipeline_router import pipeline_router as kanban_pipeline_router
from app.api.kanban.router import router as kanban_router
from app.api.machines import router as machines_router
from app.api.media import media_router
from app.api.memory.router import router as memory_router
from app.api.migration.discovery import router as migration_discovery_router
from app.api.migration.upload import router as migration_upload_router
from app.api.notifications.router import router as notifications_router
from app.api.ops.router import router as ops_router
from app.api.plugins import export_router as plugins_export_router
from app.api.plugins import import_router as plugins_import_router
from app.api.presentation import router as presentation_router
from app.api.progression import router as progression_router
from app.api.projects import router as project_router
from app.api.projects.project_state import router as project_state_router
from app.api.providers import provider_balance_router
from app.api.remote_access.router import router as remote_access_router
from app.api.risk.router import router as risk_router
from app.api.runs import router as runs_router
from app.api.runs.projection_router import projection_router as run_projection_router
from app.api.security.allowlist import router as allowlist_router
from app.api.security.estop import router as security_estop_router
from app.api.security.generate import router as security_generate_router
from app.api.security.managed_policy import router as security_managed_policy_router
from app.api.security.profiles import router as security_profiles_router
from app.api.security.router import router as security_dashboard_router
from app.api.security.vault import router as vault_router
from app.api.security.vault_credentials import router as vault_credentials_router
from app.api.security.workspace_trust import router as workspace_trust_router
from app.api.self_evolution import router as self_evolution_router
from app.api.session_map import router as session_map_router
from app.api.skill_optimization import router as skill_optimization_router
from app.api.skills import router as skills_router
from app.api.skills.evolution import router as evolution_router
from app.api.skills.growth import router as skill_growth_router
from app.api.skills.migrations import router as migrations_router
from app.api.spreadsheet import router as spreadsheet_router
from app.api.ssh_vault.router import router as ssh_vault_router
from app.api.statistics import build_statistics_router
from app.api.stt.router import router as stt_router
from app.api.stt.ws_stream import router as stt_ws_router
from app.api.system.aborted_usage_ledger_api import router as system_aborted_usage_ledger_router
from app.api.system.active_skill_telemetry_api import router as system_active_skill_telemetry_router
from app.api.system.audit_theater_api import router as system_audit_theater_router
from app.api.system.composite_usage_ledger_api import router as system_composite_usage_ledger_router
from app.api.system.context_breakdown_api import router as system_context_breakdown_router
from app.api.system.context_savings_api import router as system_context_savings_router
from app.api.system.coordination_friction_api import router as system_coordination_friction_router
from app.api.system.cron_doctor_api import router as system_cron_doctor_router
from app.api.system.custom_agent_insights_api import router as system_custom_agent_insights_router
from app.api.system.debug_share_api import router as system_debug_share_router
from app.api.system.delegation_billing_api import router as system_delegation_billing_router
from app.api.system.delivery_dossier_api import router as system_delivery_dossier_router
from app.api.system.deployment_funnel_api import router as system_deployment_funnel_router
from app.api.system.diagnostic_stream_api import router as system_diagnostic_stream_router
from app.api.system.durable_budget_ledger_api import router as system_durable_budget_ledger_router
from app.api.system.enterprise_credit_cockpit_api import router as system_enterprise_credit_cockpit_router
from app.api.system.event_causality_lineage_api import router as system_event_causality_lineage_router
from app.api.system.evidence_cross_verification_api import router as system_evidence_cross_verification_router
from app.api.system.failure_triage_api import router as system_failure_triage_router
from app.api.system.issue_ticketing_api import router as system_issue_ticketing_router
from app.api.system.knowledge_compounding_api import router as system_knowledge_compounding_router
from app.api.system.labor_acceleration_api import router as system_labor_acceleration_router
from app.api.system.local_sink_api import router as system_local_sink_router
from app.api.system.memory_backend_metrics_api import router as system_memory_backend_metrics_router
from app.api.system.model_ping_api import router as system_model_ping_router
from app.api.system.multi_tier_health_api import router as system_multi_tier_health_router
from app.api.system.multimodal_trace_api import router as system_multimodal_trace_router
from app.api.system.org_spend_limit_api import router as system_org_spend_limit_router
from app.api.system.otel_degrade_api import router as system_otel_degrade_router
from app.api.system.port_inspector import router as system_port_inspector_router
from app.api.system.rate_limit_governor_api import router as system_rate_limit_governor_router
from app.api.system.rate_limit_split_api import router as system_rate_limit_split_router
from app.api.system.reasoning_semantics_api import router as system_reasoning_semantics_router
from app.api.system.resource_ledger_api import router as system_resource_ledger_router
from app.api.system.retrieval_trace_api import router as system_retrieval_trace_router
from app.api.system.roi_analytics_api import router as system_roi_analytics_router
from app.api.system.router import router as system_router
from app.api.system.runtime_zombie_reaper_api import router as system_runtime_zombie_reaper_router
from app.api.system.sandbox_hardware_telemetry_api import router as system_sandbox_hardware_telemetry_router
from app.api.system.shutdown import router as system_shutdown_router
from app.api.system.stream_metrics_api import router as system_stream_metrics_router
from app.api.system.token_economics_api import router as system_token_economics_router
from app.api.system.turn_context_provenance_api import router as system_turn_context_provenance_router
from app.api.system.turn_usage_api import router as system_turn_usage_router
from app.api.system.unattended_coverage_api import router as system_unattended_coverage_router
from app.api.system.unattended_reliability_api import router as system_unattended_reliability_router
from app.api.system.visual_flight_recorder_api import router as system_visual_flight_recorder_router
from app.api.system.workflow_burn_api import router as system_workflow_burn_router
from app.api.system_assistant import router as system_assistant_router
from app.api.tasks.router import router as tasks_router
from app.api.theme.router import router as theme_router
from app.api.tts.router import router as tts_router
from app.api.voice.gemini_live import router as voice_gemini_live_router
from app.api.voice.realtime import router as voice_realtime_router
from app.api.voice.ws_session import router as voice_ws_router
from app.api.web_push.router import router as web_push_router
from app.api.webhook.routes import router as lifecycle_webhook_router
from app.api.widget_storage import router as widget_storage_router
from app.api.wiki import router as wiki_router
from app.api.workbench import workbench_router
from app.api.workflow.trace_router import router as workflow_trace_router
from app.api.workflow_templates import router as workflow_templates_router
from app.api.workspace.router import router as workspace_router
from app.config.deploy_mode import is_local_mode

from .system.ambient_auxiliary_accounting_api import router as system_ambient_auxiliary_router
from .system.code_freshness_api import router as system_code_freshness_router
from .system.cross_period_milestone_api import router as system_cross_period_milestone_router
from .system.dual_domain_metering_api import router as system_dual_domain_metering_router
from .system.metric_cardinality_api import router as system_metric_cardinality_router

api_router = APIRouter()

api_router.include_router(workspace_router, prefix="/workspace", tags=["workspace"])


# AI Agents

api_router.include_router(notifications_router)
api_router.include_router(web_push_router)
api_router.include_router(general_agent.router, prefix="/agents", tags=["agents"])
api_router.include_router(templates.router, prefix="/agents", tags=["agents"])
api_router.include_router(suggestions.router, prefix="/agents", tags=["agents"])
api_router.include_router(subagents.router, prefix="/chats", tags=["subagents"])
api_router.include_router(user_agent.router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(generate_prompt.router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(ai_build.router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(agent_extras.router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(agent_portability.router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(agent_history.router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(providers.router, prefix="/user-agents/providers", tags=["user-agents"])

api_router.include_router(fleet_overview_router, prefix="/agents", tags=["agents"])
api_router.include_router(fleet_telemetry_router, prefix="/agents", tags=["agents"])
api_router.include_router(governance_router, prefix="/agents", tags=["agents"])
api_router.include_router(openapi_services_router, prefix="/agents", tags=["agents"])
api_router.include_router(profile_audit_router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(readiness_router, prefix="/user-agents", tags=["user-agents"])
api_router.include_router(agent_recovery_router, prefix="", tags=["user-agents"])
api_router.include_router(goals_router)
api_router.include_router(external_agents_router, prefix="/external-agents", tags=["external-agents"])
api_router.include_router(agent_handoff_router, prefix="/agents", tags=["agents-handoff"])
api_router.include_router(device_mesh_router, prefix="/agents", tags=["device-mesh"])
api_router.include_router(todo_store_router, prefix="/agents", tags=["todo-store"])
api_router.include_router(agent_hierarchy_router, prefix="/agents", tags=["agent-hierarchy"])
api_router.include_router(split_session_goal_router, prefix="/agents", tags=["split-session-goals"])
api_router.include_router(ralph_workflow_router, prefix="/agents", tags=["ralph-workflow"])
api_router.include_router(infra_quota_router, prefix="/agents", tags=["infra-quota-governance"])
api_router.include_router(advisor_channel_router, prefix="/agents", tags=["advisor-channel"])
api_router.include_router(subagent_hub_router)
api_router.include_router(conflict_gate_router)
api_router.include_router(mcp_scope_gate_router)
api_router.include_router(agent_operations_router)
api_router.include_router(durable_dispatch_router)
api_router.include_router(report_fifo_router)
api_router.include_router(failure_facts_router)
api_router.include_router(failure_policy_router)
api_router.include_router(debate_synthesis_router)
api_router.include_router(agent_teams_router)
api_router.include_router(adaptive_wakeup_router, prefix="/agents", tags=["adaptive-wakeup"])
api_router.include_router(subagent_scaling_router, prefix="/agents", tags=["subagents-scaling"])
api_router.include_router(review_loop_router)
api_router.include_router(bot_mode_router)
api_router.include_router(squad_composition_router)
api_router.include_router(workspace_blueprint_router)
api_router.include_router(scope_guardrails_router)
api_router.include_router(autonomous_loop_router)
api_router.include_router(creator_mode_router)
api_router.include_router(tri_role_router)
api_router.include_router(skill_bundle_router)
api_router.include_router(multi_bot_focus_router)
api_router.include_router(mcp_payload_summarizer_router)
api_router.include_router(coding_wave_router)
api_router.include_router(subagent_lifecycle_router)
api_router.include_router(mixed_fleet_router)
api_router.include_router(zero_token_contract_router)
api_router.include_router(cross_surface_bridge_router)
api_router.include_router(multi_lane_router)
api_router.include_router(session_fork_router)
api_router.include_router(token_budget_governance_router)
api_router.include_router(pipeline_integrity_router)
api_router.include_router(specialist_summoning_router)
api_router.include_router(swarm_mesh_router)
api_router.include_router(workspace_inheritance_router)
api_router.include_router(replay_dedup_router)
api_router.include_router(cloud_edge_relay_router)
api_router.include_router(virtual_room_router)
api_router.include_router(swarm_offload_router)
api_router.include_router(visual_timeline_router)
api_router.include_router(clean_code_pipeline_router)
api_router.include_router(fusen_router)
api_router.include_router(vertical_presets_router)
api_router.include_router(council_router)
api_router.include_router(kanban_dispatcher_router)
api_router.include_router(cli_passthrough_router)
api_router.include_router(dag_orchestrator_router)
api_router.include_router(kanban_queue_router)
api_router.include_router(diamond_graph_router)
api_router.include_router(coauthoring_ledger_router)
api_router.include_router(socket_mesh_router)
api_router.include_router(bot_forge_router)
api_router.include_router(debate_workroom_router)

api_router.include_router(external_agent_bridge_router)
api_router.include_router(external_bundle_router)
api_router.include_router(kanban_orchestrator_router)
api_router.include_router(agent_assembler_router)
api_router.include_router(agent_avatar_router)
api_router.include_router(capability_dispatch_router)
api_router.include_router(agent_multiplexer_router)
api_router.include_router(topology_pruning_router)
api_router.include_router(memory_hub_router)

# 核心业务
api_router.include_router(approvals_router)
api_router.include_router(chat_router, prefix="/chats", tags=["chats"])
api_router.include_router(session_export_router)
api_router.include_router(group_chat_router)
api_router.include_router(project_router, prefix="/projects", tags=["projects"])
api_router.include_router(project_state_router)
api_router.include_router(files_router, prefix="/files", tags=["files"])
api_router.include_router(machines_router, prefix="", tags=["machines"])
api_router.include_router(theme_router)
api_router.include_router(
    artifact_share_public_router,
    prefix="/public/artifact-share",
    tags=["public-artifact-share"],
)
api_router.include_router(
    chat_share_public_router,
    prefix="/public/chat-share",
    tags=["public-chat-share"],
)
api_router.include_router(vault_proxy_router, prefix="/files", tags=["files"])
api_router.include_router(skills_router, prefix="/skills", tags=["skills"])
api_router.include_router(ssh_vault_router, prefix="", tags=["ssh-vault"])
api_router.include_router(browser_domain_skills_router, prefix="/browser", tags=["browser-domain-skills"])
api_router.include_router(browser_recording_router, prefix="/browser", tags=["browser-recording"])
api_router.include_router(browser_sessions_router, prefix="/browser", tags=["browser-sessions"])
api_router.include_router(browser_spaces_router, prefix="/browser", tags=["browser-spaces"])
api_router.include_router(skill_growth_router, tags=["skill-growth"])
api_router.include_router(evolution_router, tags=["evolution"])
api_router.include_router(migration_discovery_router, tags=["migration"])
api_router.include_router(migration_upload_router, tags=["migration"])
api_router.include_router(migrations_router, tags=["migrations"])
api_router.include_router(skill_optimization_router, tags=["skill-optimization"])
api_router.include_router(batch_directory_router, tags=["batch-directories"])
api_router.include_router(credentials_router, prefix="/credentials", tags=["credentials"])
api_router.include_router(memory_router, prefix="/memory", tags=["memory"])
api_router.include_router(context_bundle_router, tags=["context-bundle"])
api_router.include_router(omni_reference_router, prefix="/context", tags=["omni-reference"])
api_router.include_router(wiki_router, prefix="/wiki", tags=["wiki"])
api_router.include_router(faq_router, prefix="/faq", tags=["faq"])
api_router.include_router(widget_storage_router, tags=["widget-storage"])
api_router.include_router(cron_router, prefix="/cron", tags=["cron"])
api_router.include_router(kanban_router)
api_router.include_router(kanban_pipeline_router)
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])

api_router.include_router(background_tasks_router, prefix="/background-tasks", tags=["background-tasks"])
api_router.include_router(runs_router)
api_router.include_router(run_projection_router)
api_router.include_router(eval_router, tags=["eval"])
api_router.include_router(commerce_spending_router)

api_router.include_router(datasets_router, prefix="/datasets", tags=["datasets"])
api_router.include_router(lifecycle_webhook_router, tags=["lifecycle-webhooks"])
api_router.include_router(self_evolution_router, prefix="/self-evolution", tags=["self-evolution"])
api_router.include_router(system_assistant_router, prefix="/system-assistant", tags=["system-assistant"])
api_router.include_router(dev_ports_router, prefix="/dev-ports", tags=["dev-ports"])
api_router.include_router(presentation_router, prefix="/presentation", tags=["presentation"])
api_router.include_router(spreadsheet_router, prefix="/spreadsheet", tags=["spreadsheet"])
api_router.include_router(session_map_router, prefix="/session-map", tags=["session-map"])
api_router.include_router(workbench_router, prefix="/workbench", tags=["workbench"])

# Channels - webhook routes are dynamically registered via init_channel_routes() in main.py

if is_local_mode():
    from app.api.channels.bitable_copilot_router import (
        router as channels_bitable_copilot_router,
    )
    from app.api.channels.data_plane import router as channels_data_plane_router
    from app.api.channels.feishu_register import router as feishu_register_router
    from app.api.channels.instances import router as channels_instances_router
    from app.api.channels.instances_credentials import (
        router as channels_instances_credentials_router,
    )
    from app.api.channels.login import router as channels_login_router
    from app.api.channels.pairing_router import pairing_router as channels_pairing_router
    from app.api.channels.router import router as channels_manage_router
    from app.api.channels.test_connections import router as channels_test_router
    from app.api.channels.topics import router as channels_topics_router
    from app.api.channels.wechat import router as channels_wechat_router
    from app.api.channels.wechat_official import (
        router as channels_wechat_official_router,
    )

    api_router.include_router(channels_pairing_router, prefix="/channels/pairing", tags=["channels"])
    api_router.include_router(channels_login_router, prefix="/channels", tags=["channels"])
    api_router.include_router(channels_manage_router, prefix="/channels/manage", tags=["channels"])
    api_router.include_router(channels_test_router, prefix="/channels/manage", tags=["channels"])
    api_router.include_router(channels_wechat_router, prefix="/channels/manage", tags=["channels"])
    api_router.include_router(channels_wechat_official_router, prefix="/channels/manage", tags=["channels"])
    api_router.include_router(feishu_register_router, prefix="/channels/manage", tags=["channels"])
    api_router.include_router(channels_instances_router, prefix="/channels/manage", tags=["channels"])
    api_router.include_router(
        channels_instances_credentials_router,
        prefix="/channels/manage",
        tags=["channels"],
    )
    api_router.include_router(channels_data_plane_router, prefix="/channels/manage", tags=["channels"])
    api_router.include_router(channels_bitable_copilot_router, tags=["channels"])
    api_router.include_router(channels_topics_router, prefix="/channels/manage", tags=["channels"])

# Feature Flags
api_router.include_router(features_router, prefix="/features", tags=["features"])

# Provider Live Balance & Quotas
api_router.include_router(provider_balance_router, tags=["provider-balance"])

# User Progression
api_router.include_router(progression_router, prefix="/progression", tags=["progression"])

# Agent Plugins (Agent Plugins 1.0.0 import / expert export)
api_router.include_router(plugins_import_router, prefix="/plugins", tags=["plugins"])
api_router.include_router(plugins_export_router, prefix="/plugins", tags=["plugins"])

# 集成与基础设施
api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])
api_router.include_router(connect_router, tags=["connect"])
api_router.include_router(config_router, prefix="/config", tags=["config"])
api_router.include_router(
    model_overrides_router,
    prefix="/settings/model-overrides",
    tags=["settings", "model-overrides"],
)
api_router.include_router(allowlist_router, prefix="/security/allowlist", tags=["security"])
api_router.include_router(workspace_trust_router, prefix="/security/workspace-trust", tags=["security"])
api_router.include_router(security_estop_router, tags=["security"])
api_router.include_router(security_dashboard_router, tags=["security"])
api_router.include_router(security_generate_router, tags=["security"])
api_router.include_router(security_profiles_router, tags=["security"])
api_router.include_router(security_managed_policy_router, tags=["security"])
api_router.include_router(vault_router, prefix="/security", tags=["security"])
api_router.include_router(vault_credentials_router, prefix="/security", tags=["security"])
api_router.include_router(risk_router, prefix="/risk", tags=["risk"])
api_router.include_router(audit_router, tags=["audit"])
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(ops_router)
api_router.include_router(checkpoint_router, tags=["checkpoint"])
api_router.include_router(stt_router, prefix="/stt", tags=["stt"])
api_router.include_router(stt_ws_router, prefix="/ws/stt", tags=["stt"])
api_router.include_router(tts_router, prefix="/tts", tags=["tts"])
api_router.include_router(voice_ws_router, prefix="/ws/voice", tags=["voice"])
api_router.include_router(voice_realtime_router, prefix="/voice", tags=["voice"])
api_router.include_router(voice_gemini_live_router, prefix="/voice", tags=["voice"])
api_router.include_router(artifact_mappings_router, prefix="/config", tags=["config"])
api_router.include_router(build_statistics_router(), prefix="/statistics", tags=["statistics"])
api_router.include_router(system_router, prefix="/system", tags=["system"])
api_router.include_router(instance_archive_router, prefix="/instance-archive", tags=["instance-archive"])
api_router.include_router(system_shutdown_router, prefix="/system", tags=["system"])
api_router.include_router(system_port_inspector_router, prefix="/system", tags=["system"])
api_router.include_router(system_multi_tier_health_router, prefix="/system", tags=["system"])
api_router.include_router(system_failure_triage_router, prefix="/system", tags=["system"])
api_router.include_router(system_retrieval_trace_router, prefix="/system", tags=["system"])
api_router.include_router(system_resource_ledger_router, prefix="/system", tags=["system"])
api_router.include_router(system_labor_acceleration_router, prefix="/system", tags=["system"])
api_router.include_router(system_issue_ticketing_router, prefix="/system", tags=["system"])
api_router.include_router(system_workflow_burn_router, prefix="/system", tags=["system"])
api_router.include_router(system_coordination_friction_router, prefix="/system", tags=["system"])
api_router.include_router(system_cron_doctor_router, prefix="/system", tags=["system"])
api_router.include_router(system_debug_share_router, prefix="/system", tags=["system"])
api_router.include_router(system_token_economics_router, prefix="/system", tags=["system"])
api_router.include_router(system_delivery_dossier_router, prefix="/system", tags=["system"])
api_router.include_router(system_rate_limit_governor_router, prefix="/system", tags=["system"])
api_router.include_router(system_context_savings_router, prefix="/system", tags=["system"])
api_router.include_router(system_reasoning_semantics_router, prefix="/system", tags=["system"])
api_router.include_router(system_org_spend_limit_router, prefix="/system", tags=["system"])
api_router.include_router(system_knowledge_compounding_router, prefix="/system", tags=["system"])
api_router.include_router(system_turn_context_provenance_router, prefix="/system", tags=["system"])
api_router.include_router(system_deployment_funnel_router, prefix="/system", tags=["system"])
api_router.include_router(system_stream_metrics_router, prefix="/system", tags=["system"])
api_router.include_router(system_otel_degrade_router, prefix="/system", tags=["system"])
api_router.include_router(system_diagnostic_stream_router, prefix="/system", tags=["system"])
api_router.include_router(system_turn_usage_router, prefix="/system", tags=["system"])
api_router.include_router(system_context_breakdown_router, prefix="/system", tags=["system"])
api_router.include_router(system_local_sink_router, prefix="/system", tags=["system"])
api_router.include_router(system_rate_limit_split_router, prefix="/system", tags=["system"])
api_router.include_router(system_enterprise_credit_cockpit_router, prefix="/system", tags=["system"])
api_router.include_router(system_unattended_reliability_router, prefix="/system", tags=["system"])
api_router.include_router(system_custom_agent_insights_router, prefix="/system", tags=["system"])
api_router.include_router(system_evidence_cross_verification_router, prefix="/system", tags=["system"])
api_router.include_router(system_composite_usage_ledger_router, prefix="/system", tags=["system"])
api_router.include_router(system_ambient_auxiliary_router, prefix="/system", tags=["system"])
api_router.include_router(system_code_freshness_router, prefix="/system", tags=["system"])
api_router.include_router(system_cross_period_milestone_router, prefix="/system", tags=["system"])
api_router.include_router(system_dual_domain_metering_router, prefix="/system", tags=["system"])
api_router.include_router(system_metric_cardinality_router, prefix="/system", tags=["system"])
api_router.include_router(system_event_causality_lineage_router, prefix="/system", tags=["system"])
api_router.include_router(system_multimodal_trace_router, prefix="/system", tags=["system"])
api_router.include_router(system_visual_flight_recorder_router, prefix="/system", tags=["system"])
api_router.include_router(system_sandbox_hardware_telemetry_router, prefix="/system", tags=["system"])
api_router.include_router(system_runtime_zombie_reaper_router, prefix="/system", tags=["system"])
api_router.include_router(system_delegation_billing_router, prefix="/system", tags=["system"])
api_router.include_router(system_audit_theater_router, prefix="/system", tags=["system"])
api_router.include_router(system_memory_backend_metrics_router, prefix="/system", tags=["system"])
api_router.include_router(system_aborted_usage_ledger_router, prefix="/system", tags=["system"])
api_router.include_router(system_active_skill_telemetry_router, prefix="/system", tags=["system"])
api_router.include_router(system_durable_budget_ledger_router, prefix="/system", tags=["system"])
api_router.include_router(system_unattended_coverage_router, prefix="/system", tags=["system"])
api_router.include_router(system_model_ping_router)
api_router.include_router(system_roi_analytics_router)
api_router.include_router(git_worktree_router)
api_router.include_router(remote_access_router, prefix="/remote-access", tags=["remote-access"])

api_router.include_router(budget_router, prefix="/budget", tags=["budget"])
api_router.include_router(api_keys_router)
api_router.include_router(companion_router, prefix="/companion", tags=["companion"])
api_router.include_router(companion_doctor_router, prefix="/companion", tags=["companion"])
api_router.include_router(compounding_playbook_router, tags=["compounding-playbook"])
api_router.include_router(workflow_templates_router, tags=["workflow-templates"])
api_router.include_router(workflow_trace_router, tags=["workflow-trace"])
api_router.include_router(media_router, prefix="/media", tags=["media"])
api_router.include_router(client_logs_router, tags=["logs"])
api_router.include_router(a2a_router, prefix="/a2a", tags=["a2a"])

# 本地模式：事件通知（SSE）
if is_local_mode():
    from app.api.events import router as events_router

    api_router.include_router(events_router, tags=["events"])

api_router.include_router(extension_router, tags=["extension"])
api_router.include_router(extension_ws_router, prefix="/ws", tags=["extension"])
