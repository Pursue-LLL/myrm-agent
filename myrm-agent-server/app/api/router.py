from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.agents import agent as user_agent
from app.api.agents import (
    agent_history,
    general_agent,
    generate_prompt,
    harness_router,
    media,
    providers,
    session,
    subagents,
    suggestions,
    templates,
)
from app.api.agents.openapi_services import router as openapi_services_router
from app.api.api_keys import router as api_keys_router
from app.api.approvals import router as approvals_router
from app.api.audit.auth_router import router as auth_audit_router
from app.api.audit.bash_router import router as audit_router
from app.api.background_tasks.router import router as background_tasks_router
from app.api.batch_optimization import router as batch_optimization_router
from app.api.budget import budget_router
from app.api.calendar.router import router as calendar_router
from app.api.channels.channel_ingress import router as channel_ingress_router
from app.api.chats import router as chat_router
from app.api.checkpoint import router as checkpoint_router
from app.api.client_logs import router as client_logs_router
from app.api.commitment.router import router as commitment_router
from app.api.companion.router import router as companion_router
from app.api.config.artifact_mappings import router as artifact_mappings_router
from app.api.config.router import router as config_router
from app.api.connect.router import router as connect_router
from app.api.credentials.router import router as credentials_router
from app.api.cron.routes import router as cron_router
from app.api.eval.router import router as eval_router
from app.api.external_agents import router as external_agents_router
from app.api.features.router import router as features_router
from app.api.files.router import router as files_router
from app.api.files.vault_proxy import router as vault_proxy_router
from app.api.goals.router import router as goals_router
from app.api.health.diagnostic import router as diagnostic_router
from app.api.health.router import router as health_router
from app.api.integrations import router as integrations_router
from app.api.kanban.pipeline_router import pipeline_router as kanban_pipeline_router
from app.api.kanban.router import router as kanban_router
from app.api.local_file_search.router import router as local_file_search_router
from app.api.media import media_router
from app.api.memory.router import router as memory_router
from app.api.message_filter import router as message_filter_router
from app.api.migration.discovery import router as migration_discovery_router
from app.api.notifications.router import router as notifications_router
from app.api.projects import router as project_router
from app.api.risk.router import router as risk_router
from app.api.security.allowlist import router as allowlist_router
from app.api.security.generate import router as security_generate_router
from app.api.security.profiles import router as security_profiles_router
from app.api.security.router import router as security_dashboard_router
from app.api.security.vault import router as vault_router
from app.api.skill_optimization import router as skill_optimization_router
from app.api.skill_optimization import ws_router as skill_optimization_ws_router
from app.api.skills import router as skills_router
from app.api.skills.evolution import router as evolution_router
from app.api.skills.experience_ledger import router as experience_ledger_router
from app.api.skills.growth import router as skill_growth_router
from app.api.skills.migrations import router as migrations_router
from app.api.skills.quality import router as skill_quality_router
from app.api.skills.reviews import router as reviews_router
from app.api.skills.ws_evolution import router as evolution_ws_router
from app.api.statistics import build_statistics_router
from app.api.stt.router import router as stt_router
from app.api.stt.ws_stream import router as stt_ws_router
from app.api.system.router import router as system_router
from app.api.system.shutdown import router as system_shutdown_router
from app.api.tasks.router import router as tasks_router
from app.api.tts.router import router as tts_router
from app.api.voice.realtime import router as voice_realtime_router
from app.api.voice.ws_session import router as voice_ws_router
from app.api.wiki import router as wiki_router
from app.api.workspace_rules import router as workspace_rules_router
from app.config.deploy_mode import is_local_mode

api_router = APIRouter()


# Agent interrupt endpoint (called by CP pipeline to stop running agents)
@api_router.post("/agent/interrupt", tags=["agents"])
async def interrupt_agent(request: Request) -> JSONResponse:
    """Interrupt all running agents for the authenticated user."""
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    interrupted = gateway.interrupt()
    return JSONResponse({"interrupted": interrupted})


# AI Agents

api_router.include_router(notifications_router)
api_router.include_router(channel_ingress_router, tags=["channels"])
api_router.include_router(general_agent.router, prefix="/agents", tags=["agents"])
api_router.include_router(templates.router, prefix="/agents", tags=["agents"])
api_router.include_router(suggestions.router, prefix="/agents", tags=["agents"])
api_router.include_router(media.router, prefix="/agents", tags=["agents"])
api_router.include_router(session.router, prefix="/agents", tags=["agents"])
api_router.include_router(subagents.router, prefix="/chats", tags=["subagents"])
api_router.include_router(harness_router.router, prefix="/agents", tags=["agents"])
api_router.include_router(
    user_agent.router, prefix="/user-agents", tags=["user-agents"]
)
api_router.include_router(
    generate_prompt.router, prefix="/user-agents", tags=["user-agents"]
)
api_router.include_router(
    agent_history.router, prefix="/user-agents", tags=["user-agents"]
)
api_router.include_router(
    providers.router, prefix="/user-agents/providers", tags=["user-agents"]
)

api_router.include_router(openapi_services_router, prefix="/agents", tags=["agents"])
api_router.include_router(goals_router)
api_router.include_router(
    external_agents_router, prefix="/external-agents", tags=["external-agents"]
)

# 核心业务
api_router.include_router(approvals_router)
api_router.include_router(chat_router, prefix="/chats", tags=["chats"])
api_router.include_router(project_router, prefix="/projects", tags=["projects"])
api_router.include_router(files_router, prefix="/files", tags=["files"])
api_router.include_router(vault_proxy_router, prefix="/files", tags=["files"])
api_router.include_router(skills_router, prefix="/skills", tags=["skills"])
api_router.include_router(skill_growth_router, tags=["skill-growth"])
api_router.include_router(skill_quality_router, tags=["skill-quality"])
api_router.include_router(evolution_router, tags=["evolution"])
api_router.include_router(evolution_ws_router, prefix="/ws", tags=["evolution"])
api_router.include_router(experience_ledger_router, tags=["experience-ledger"])
api_router.include_router(migration_discovery_router, tags=["migration"])
api_router.include_router(migrations_router, tags=["migrations"])
api_router.include_router(reviews_router, tags=["reviews"])
api_router.include_router(skill_optimization_router, tags=["skill-optimization"])
api_router.include_router(batch_optimization_router, tags=["batch-optimization"])
api_router.include_router(
    credentials_router, prefix="/credentials", tags=["credentials"]
)
api_router.include_router(memory_router, prefix="/memory", tags=["memory"])
api_router.include_router(wiki_router, prefix="/wiki", tags=["wiki"])
api_router.include_router(cron_router, prefix="/cron", tags=["cron"])
api_router.include_router(calendar_router)
api_router.include_router(commitment_router)
api_router.include_router(kanban_router)
api_router.include_router(kanban_pipeline_router)
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])

api_router.include_router(
    background_tasks_router, prefix="/background-tasks", tags=["background-tasks"]
)
api_router.include_router(eval_router, tags=["eval"])

# Channels - webhook routes are dynamically registered via init_channel_routes() in main.py

if is_local_mode():
    from app.api.channels.dlq import router as channels_dlq_router
    from app.api.channels.feishu_register import router as feishu_register_router
    from app.api.channels.instances import router as channels_instances_router
    from app.api.channels.login import router as channels_login_router
    from app.api.channels.router import router as channels_manage_router
    from app.api.channels.routes_management import router as routes_management_router
    from app.api.channels.test_connections import router as channels_test_router
    from app.api.channels.topics import router as channels_topics_router
    from app.api.channels.wechat import router as channels_wechat_router

    api_router.include_router(
        channels_login_router, prefix="/channels", tags=["channels"]
    )
    api_router.include_router(
        channels_manage_router, prefix="/channels/manage", tags=["channels"]
    )
    api_router.include_router(
        channels_test_router, prefix="/channels/manage", tags=["channels"]
    )
    api_router.include_router(
        channels_wechat_router, prefix="/channels/manage", tags=["channels"]
    )
    api_router.include_router(
        feishu_register_router, prefix="/channels/manage", tags=["channels"]
    )
    api_router.include_router(
        channels_instances_router, prefix="/channels/manage", tags=["channels"]
    )
    api_router.include_router(
        channels_topics_router, prefix="/channels/manage", tags=["channels"]
    )
    api_router.include_router(
        routes_management_router, prefix="/channels/routes", tags=["channels"]
    )
    api_router.include_router(
        channels_dlq_router, prefix="/channels/dlq", tags=["channels"]
    )

# Feature Flags
api_router.include_router(features_router, prefix="/features", tags=["features"])

# 集成与基础设施
api_router.include_router(integrations_router, tags=["integrations"])
api_router.include_router(connect_router, tags=["connect"])
api_router.include_router(config_router, prefix="/config", tags=["config"])
api_router.include_router(
    allowlist_router, prefix="/security/allowlist", tags=["security"]
)
api_router.include_router(security_dashboard_router, tags=["security"])
api_router.include_router(security_generate_router, tags=["security"])
api_router.include_router(security_profiles_router, tags=["security"])
api_router.include_router(vault_router, prefix="/security", tags=["security"])
api_router.include_router(message_filter_router, tags=["message-filter"])
api_router.include_router(risk_router, prefix="/risk", tags=["risk"])
api_router.include_router(auth_audit_router, tags=["audit"])
api_router.include_router(audit_router, tags=["audit"])
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(diagnostic_router, prefix="/diagnostic", tags=["diagnostic"])
api_router.include_router(checkpoint_router, tags=["checkpoint"])
api_router.include_router(stt_router, prefix="/stt", tags=["stt"])
api_router.include_router(stt_ws_router, prefix="/ws/stt", tags=["stt"])
api_router.include_router(
    skill_optimization_ws_router,
    prefix="/ws/skill-optimization",
    tags=["skill-optimization"],
)
api_router.include_router(tts_router, prefix="/tts", tags=["tts"])
api_router.include_router(voice_ws_router, prefix="/ws/voice", tags=["voice"])
api_router.include_router(voice_realtime_router, prefix="/voice", tags=["voice"])
api_router.include_router(artifact_mappings_router, prefix="/config", tags=["config"])
api_router.include_router(
    build_statistics_router(), prefix="/statistics", tags=["statistics"]
)
api_router.include_router(system_router, prefix="/system", tags=["system"])
api_router.include_router(system_shutdown_router, prefix="/system", tags=["system"])

api_router.include_router(budget_router, prefix="/budget", tags=["budget"])
api_router.include_router(workspace_rules_router, tags=["workspace"])
api_router.include_router(api_keys_router)
api_router.include_router(companion_router, prefix="/companion", tags=["companion"])
api_router.include_router(
    local_file_search_router, prefix="/local-file-search", tags=["local-file-search"]
)
api_router.include_router(media_router, prefix="/media", tags=["media"])
api_router.include_router(client_logs_router, tags=["logs"])

# Agent Events（仅本地模式）
if is_local_mode():
    from app.api.events import router as events_router

    api_router.include_router(events_router, tags=["events"])
