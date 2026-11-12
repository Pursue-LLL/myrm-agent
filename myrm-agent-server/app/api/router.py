"""API route table: every router mounted under the API prefix, declared as data.

[INPUT]
- app.server.lazy_routes::RouterMount / LazyRouteLoader (POS: lazily imported route groups)
- app.config.deploy_mode::is_local_mode (POS: gates the local-mode-only mounts)

[OUTPUT]
- ROUTER_MOUNTS: every mount in declaration order, with the route segment it serves
- route_loader: the loader that imports a mount's group when a request needs it
- api_router: the aggregate router of ``route_loader``, included by ``app.main`` under ``settings.api_prefix``

[POS]
The single registry of the server's REST and WebSocket routers. A mount names its module instead of importing it, so
launching the server does not import the routers; ``route_loader`` imports a segment's mounts on its first request or
in the background after startup (see ``app.server.lazy_routes``).
``segment`` is the first path segment below the API prefix that every route of the mount serves; mounts of one segment
load together. ``tests/architecture/test_route_table.py`` pins each mount to its segment.
"""

from app.config.deploy_mode import is_local_mode
from app.server.lazy_routes import LazyRouteLoader, RouterMount

ROUTER_MOUNTS: tuple[RouterMount, ...] = (
    RouterMount("workspace", "app.api.workspace.router", prefix="/workspace", tags=("workspace",)),
    # AI Agents
    RouterMount("notifications", "app.api.notifications.router"),
    RouterMount("web-push", "app.api.web_push.router"),
    RouterMount("agents", "app.api.agents.general_agent", prefix="/agents", tags=("agents",)),
    RouterMount("agents", "app.api.agents.templates", prefix="/agents", tags=("agents",)),
    RouterMount("agents", "app.api.agents.subagent_presets", prefix="/agents", tags=("agents",)),
    RouterMount("agents", "app.api.agents.suggestions", prefix="/agents", tags=("agents",)),
    RouterMount("chats", "app.api.agents.subagents", prefix="/chats", tags=("subagents",)),
    RouterMount("user-agents", "app.api.agents.agent", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("user-agents", "app.api.agents.generate_prompt", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("user-agents", "app.api.agents.ai_build", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("user-agents", "app.api.agents.agent_extras", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("user-agents", "app.api.agents.agent_portability", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("user-agents", "app.api.agents.agent_history", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("user-agents", "app.api.agents.providers", prefix="/user-agents/providers", tags=("user-agents",)),
    RouterMount("agents", "app.api.agents.fleet_overview", prefix="/agents", tags=("agents",)),
    RouterMount("agents", "app.api.agents.governance", prefix="/agents", tags=("agents",)),
    RouterMount("agents", "app.api.agents.openapi_services", prefix="/agents", tags=("agents",)),
    RouterMount("user-agents", "app.api.agents.profile_audit", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("user-agents", "app.api.agents.readiness", prefix="/user-agents", tags=("user-agents",)),
    RouterMount("agents", "app.api.agents.recovery", tags=("user-agents",)),
    RouterMount("goals", "app.api.goals.router"),
    RouterMount("external-agents", "app.api.external_agents", prefix="/external-agents", tags=("external-agents",)),
    # Core business
    RouterMount("approvals", "app.api.approvals"),
    RouterMount("chats", "app.api.chats", prefix="/chats", tags=("chats",)),
    RouterMount("projects", "app.api.projects", prefix="/projects", tags=("projects",)),
    RouterMount("files", "app.api.files.router", prefix="/files", tags=("files",)),
    RouterMount("theme", "app.api.theme.router"),
    RouterMount(
        "public",
        "app.api.files.artifact_share_api",
        attr="public_router",
        prefix="/public/artifact-share",
        tags=("public-artifact-share",),
    ),
    RouterMount(
        "public", "app.api.chats.chat.share", attr="public_router", prefix="/public/chat-share", tags=("public-chat-share",)
    ),
    RouterMount("files", "app.api.files.vault_proxy", prefix="/files", tags=("files",)),
    RouterMount("skills", "app.api.skills", prefix="/skills", tags=("skills",)),
    RouterMount("ssh-vault", "app.api.ssh_vault.router", tags=("ssh-vault",)),
    RouterMount("browser", "app.api.browser_domain_skills", prefix="/browser", tags=("browser-domain-skills",)),
    RouterMount("browser", "app.api.browser_recording", prefix="/browser", tags=("browser-recording",)),
    RouterMount("browser", "app.api.browser_sessions", prefix="/browser", tags=("browser-sessions",)),
    RouterMount("skill-growth", "app.api.skills.growth", tags=("skill-growth",)),
    RouterMount("evolution", "app.api.skills.evolution", tags=("evolution",)),
    RouterMount("migration", "app.api.migration.discovery", tags=("migration",)),
    RouterMount("migration", "app.api.migration.upload", tags=("migration",)),
    RouterMount("migrations", "app.api.skills.migrations", tags=("migrations",)),
    RouterMount("skill-optimization", "app.api.skill_optimization", tags=("skill-optimization",)),
    RouterMount("batch-directories", "app.api.batch_directory", tags=("batch-directories",)),
    RouterMount("credentials", "app.api.credentials.router", prefix="/credentials", tags=("credentials",)),
    RouterMount("memory", "app.api.memory.router", prefix="/memory", tags=("memory",)),
    RouterMount("context-bundle", "app.api.context.router", tags=("context-bundle",)),
    RouterMount("wiki", "app.api.wiki", prefix="/wiki", tags=("wiki",)),
    RouterMount("faq", "app.api.faq", prefix="/faq", tags=("faq",)),
    RouterMount("widget-storage", "app.api.widget_storage", tags=("widget-storage",)),
    RouterMount("cron", "app.api.cron.routes", prefix="/cron", tags=("cron",)),
    RouterMount("kanban", "app.api.kanban.router"),
    RouterMount("kanban", "app.api.kanban.pipeline_router", attr="pipeline_router"),
    RouterMount("tasks", "app.api.tasks.router", prefix="/tasks", tags=("tasks",)),
    RouterMount("background-tasks", "app.api.background_tasks.router", prefix="/background-tasks", tags=("background-tasks",)),
    RouterMount("runs", "app.api.runs"),
    RouterMount("eval", "app.api.eval.router", tags=("eval",)),
    RouterMount("commerce", "app.api.commerce.spending_router"),
    RouterMount("datasets", "app.api.datasets", prefix="/datasets", tags=("datasets",)),
    RouterMount("lifecycle-webhooks", "app.api.webhook.routes", tags=("lifecycle-webhooks",)),
    RouterMount("self-evolution", "app.api.self_evolution", prefix="/self-evolution", tags=("self-evolution",)),
    RouterMount("system-assistant", "app.api.system_assistant", prefix="/system-assistant", tags=("system-assistant",)),
    RouterMount("dev-ports", "app.api.dev_ports", prefix="/dev-ports", tags=("dev-ports",)),
    RouterMount("presentation", "app.api.presentation", prefix="/presentation", tags=("presentation",)),
    RouterMount("spreadsheet", "app.api.spreadsheet", prefix="/spreadsheet", tags=("spreadsheet",)),
    RouterMount("session-map", "app.api.session_map", prefix="/session-map", tags=("session-map",)),
    RouterMount("workbench", "app.api.workbench", attr="workbench_router", prefix="/workbench", tags=("workbench",)),
    # Channels (local mode); webhook routes are registered dynamically by init_channel_routes() during startup
    RouterMount("channels", "app.api.channels.login", prefix="/channels", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.router", prefix="/channels/manage", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.test_connections", prefix="/channels/manage", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.wechat", prefix="/channels/manage", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.wechat_official", prefix="/channels/manage", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.feishu_register", prefix="/channels/manage", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.instances", prefix="/channels/manage", tags=("channels",), local_only=True),
    RouterMount(
        "channels", "app.api.channels.instances_credentials", prefix="/channels/manage", tags=("channels",), local_only=True
    ),
    RouterMount("channels", "app.api.channels.data_plane", prefix="/channels/manage", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.bitable_copilot_router", tags=("channels",), local_only=True),
    RouterMount("channels", "app.api.channels.topics", prefix="/channels/manage", tags=("channels",), local_only=True),
    # Feature flags
    RouterMount("features", "app.api.features.router", prefix="/features", tags=("features",)),
    # Provider live balance and quotas
    RouterMount("providers", "app.api.providers", attr="provider_balance_router", tags=("provider-balance",)),
    # User progression
    RouterMount("progression", "app.api.progression", prefix="/progression", tags=("progression",)),
    # Agent Plugins (import / expert export)
    RouterMount("plugins", "app.api.plugins", attr="import_router", prefix="/plugins", tags=("plugins",)),
    RouterMount("plugins", "app.api.plugins", attr="export_router", prefix="/plugins", tags=("plugins",)),
    # Integrations and infrastructure
    RouterMount("integrations", "app.api.integrations", prefix="/integrations", tags=("integrations",)),
    RouterMount("connect", "app.api.connect.router", tags=("connect",)),
    RouterMount("config", "app.api.config.router", prefix="/config", tags=("config",)),
    RouterMount("security", "app.api.security.allowlist", prefix="/security/allowlist", tags=("security",)),
    RouterMount("security", "app.api.security.workspace_trust", prefix="/security/workspace-trust", tags=("security",)),
    RouterMount("security", "app.api.security.estop", tags=("security",)),
    RouterMount("security", "app.api.security.router", tags=("security",)),
    RouterMount("security", "app.api.security.generate", tags=("security",)),
    RouterMount("security", "app.api.security.profiles", tags=("security",)),
    RouterMount("security", "app.api.security.managed_policy", tags=("security",)),
    RouterMount("security", "app.api.security.vault", prefix="/security", tags=("security",)),
    RouterMount("security", "app.api.security.vault_credentials", prefix="/security", tags=("security",)),
    RouterMount("risk", "app.api.risk.router", prefix="/risk", tags=("risk",)),
    RouterMount("audit", "app.api.audit.bash_router", tags=("audit",)),
    RouterMount("health", "app.api.health.router", prefix="/health", tags=("health",)),
    RouterMount("ops", "app.api.ops.router"),
    RouterMount("checkpoint", "app.api.checkpoint", tags=("checkpoint",)),
    RouterMount("stt", "app.api.stt.router", prefix="/stt", tags=("stt",)),
    RouterMount("ws", "app.api.stt.ws_stream", prefix="/ws/stt", tags=("stt",)),
    RouterMount("tts", "app.api.tts.router", prefix="/tts", tags=("tts",)),
    RouterMount("ws", "app.api.voice.ws_session", prefix="/ws/voice", tags=("voice",)),
    RouterMount("voice", "app.api.voice.realtime", prefix="/voice", tags=("voice",)),
    RouterMount("voice", "app.api.voice.gemini_live", prefix="/voice", tags=("voice",)),
    RouterMount("config", "app.api.config.artifact_mappings", prefix="/config", tags=("config",)),
    RouterMount(
        "statistics",
        "app.api.statistics",
        attr="build_statistics_router",
        prefix="/statistics",
        tags=("statistics",),
        factory=True,
    ),
    RouterMount("system", "app.api.system.router", prefix="/system", tags=("system",)),
    RouterMount("instance-archive", "app.api.instance_archive.router", prefix="/instance-archive", tags=("instance-archive",)),
    RouterMount("system", "app.api.system.shutdown", prefix="/system", tags=("system",)),
    RouterMount("system", "app.api.system.model_ping_api"),
    RouterMount("remote-access", "app.api.remote_access.router", prefix="/remote-access", tags=("remote-access",)),
    RouterMount("budget", "app.api.budget", attr="budget_router", prefix="/budget", tags=("budget",)),
    RouterMount("api-keys", "app.api.api_keys"),
    RouterMount("companion", "app.api.companion.router", prefix="/companion", tags=("companion",)),
    RouterMount("companion", "app.api.companion.doctor_router", prefix="/companion", tags=("companion",)),
    RouterMount("compounding-playbook", "app.api.compounding_playbook", tags=("compounding-playbook",)),
    RouterMount("workflow-templates", "app.api.workflow_templates", tags=("workflow-templates",)),
    RouterMount("media", "app.api.media", attr="media_router", prefix="/media", tags=("media",)),
    RouterMount("logs", "app.api.client_logs", tags=("logs",)),
    # Local mode: event notifications (SSE)
    RouterMount("notifications", "app.api.events", tags=("events",), local_only=True),
    RouterMount("extension", "app.api.extension", tags=("extension",)),
    RouterMount("ws", "app.api.extension", attr="ws_router", prefix="/ws", tags=("extension",)),
)

# The health probes (desktop watchdog, orchestrators) answer from the first request, so their routers are mounted at import time.
EAGER_SEGMENTS = ("health",)

route_loader = LazyRouteLoader(ROUTER_MOUNTS, local_mode=is_local_mode(), eager_segments=EAGER_SEGMENTS)
api_router = route_loader.router
