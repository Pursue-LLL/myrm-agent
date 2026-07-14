"""[INPUT]
- app.config.settings::settings (POS: 统一配置中心)
- app.api.* routers (POS: 各 API 路由模块，按需 lazy import)
- app.server.exceptions / app.core.utils.errors (POS: 异常处理器，可选注册)

[OUTPUT]
- build_minimal_app(): 按 router key / preset 构建轻量 FastAPI 测试应用
- preset_for_test_path(): 从测试文件路径推断 preset
- build_openai_compat_test_app(): OpenAI 兼容层 + API keys 组合应用

[POS]
测试专用 FastAPI 工厂。仅挂载被测路由，避免 import app.main 拉满依赖栈。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from fastapi import APIRouter, FastAPI

from app.config.settings import settings

API_PREFIX = settings.api_prefix


@dataclass(frozen=True, slots=True)
class _RouterMount:
    module: str
    attr: str = "router"
    prefix: str = ""
    tags: tuple[str, ...] = ()
    factory: bool = False


def _mount(api: APIRouter, spec: _RouterMount) -> None:
    mod = import_module(spec.module)
    target = getattr(mod, spec.attr)
    if spec.factory:
        target = target()
    kwargs: dict[str, Any] = {}
    if spec.prefix:
        kwargs["prefix"] = spec.prefix
    if spec.tags:
        kwargs["tags"] = list(spec.tags)
    api.include_router(target, **kwargs)


# Keys mirror app.api.router mounts; each import is lazy (only requested routers load).
_ROUTER_MOUNTS: dict[str, _RouterMount] = {
    "workspace": _RouterMount("app.api.workspace.router", prefix="/workspace", tags=("workspace",)),
    "notifications": _RouterMount("app.api.notifications.router"),
    "agents_general": _RouterMount("app.api.agents.general_agent", prefix="/agents", tags=("agents",)),
    "agents_templates": _RouterMount("app.api.agents.templates", prefix="/agents", tags=("agents",)),
    "agents_subagents": _RouterMount("app.api.agents.subagents", prefix="/chats", tags=("subagents",)),
    "user_agents": _RouterMount("app.api.agents.agent", prefix="/user-agents", tags=("user-agents",)),
    "generate_prompt": _RouterMount("app.api.agents.generate_prompt", prefix="/user-agents", tags=("user-agents",)),
    "ai_build": _RouterMount("app.api.agents.ai_build", prefix="/user-agents", tags=("user-agents",)),
    "agent_history": _RouterMount("app.api.agents.agent_history", prefix="/user-agents", tags=("user-agents",)),
    "openapi_services": _RouterMount("app.api.agents.openapi_services", attr="router", prefix="/agents", tags=("agents",)),
    "fleet_overview": _RouterMount("app.api.agents.fleet_overview", prefix="/agents", tags=("agents",)),
    "goals": _RouterMount("app.api.goals.router"),
    "external_agents": _RouterMount("app.api.external_agents", prefix="/external-agents", tags=("external-agents",)),
    "approvals": _RouterMount("app.api.approvals"),
    "chats": _RouterMount("app.api.chats", prefix="/chats", tags=("chats",)),
    "projects": _RouterMount("app.api.projects", prefix="/projects", tags=("projects",)),
    "files": _RouterMount("app.api.files.router", prefix="/files", tags=("files",)),
    "artifact_share_public": _RouterMount(
        "app.api.files.artifact_share_api",
        attr="public_router",
        prefix="/public/artifact-share",
        tags=("public-artifact-share",),
    ),
    "vault_proxy": _RouterMount("app.api.files.vault_proxy", prefix="/files", tags=("files",)),
    "skills": _RouterMount("app.api.skills", prefix="/skills", tags=("skills",)),
    "skill_growth": _RouterMount("app.api.skills.growth", tags=("skill-growth",)),
    "skill_quality": _RouterMount("app.api.skills.quality", tags=("skill-quality",)),
    "evolution": _RouterMount("app.api.skills.evolution", tags=("evolution",)),
    "evolution_ws": _RouterMount("app.api.skills.ws_evolution", prefix="/ws", tags=("evolution",)),
    "experience_ledger": _RouterMount("app.api.skills.experience_ledger", tags=("experience-ledger",)),
    "migration_discovery": _RouterMount("app.api.migration.discovery", tags=("migration",)),
    "migration_upload": _RouterMount("app.api.migration.upload", tags=("migration",)),
    "migrations": _RouterMount("app.api.skills.migrations", tags=("migrations",)),
    "reviews": _RouterMount("app.api.skills.reviews", tags=("reviews",)),
    "memory": _RouterMount("app.api.memory.router", prefix="/memory", tags=("memory",)),
    "context_bundle": _RouterMount("app.api.context.router", tags=("context-bundle",)),
    "wiki": _RouterMount("app.api.wiki", prefix="/wiki", tags=("wiki",)),
    "cron": _RouterMount("app.api.cron.routes", prefix="/cron", tags=("cron",)),
    "eval": _RouterMount("app.api.eval.router", tags=("eval",)),
    "integrations": _RouterMount("app.api.integrations", prefix="/integrations", tags=("integrations",)),
    "connect": _RouterMount("app.api.connect.router", tags=("connect",)),
    "config": _RouterMount("app.api.config.router", prefix="/config", tags=("config",)),
    "artifact_mappings": _RouterMount("app.api.config.artifact_mappings", prefix="/config", tags=("config",)),
    "allowlist": _RouterMount("app.api.security.allowlist", prefix="/security/allowlist", tags=("security",)),
    "security_estop": _RouterMount("app.api.security.estop", tags=("security",)),
    "security_dashboard": _RouterMount("app.api.security.router", tags=("security",)),
    "security_generate": _RouterMount("app.api.security.generate", tags=("security",)),
    "security_profiles": _RouterMount("app.api.security.profiles", tags=("security",)),
    "vault": _RouterMount("app.api.security.vault", prefix="/security", tags=("security",)),
    "vault_credentials": _RouterMount("app.api.security.vault_credentials", prefix="/security", tags=("security",)),
    "health": _RouterMount("app.api.health.router", prefix="/health", tags=("health",)),
    "diagnostic": _RouterMount("app.api.health.diagnostic", prefix="/diagnostic", tags=("diagnostic",)),
    "checkpoint": _RouterMount("app.api.checkpoint", tags=("checkpoint",)),
    "statistics": _RouterMount("app.api.statistics", attr="build_statistics_router", factory=True, prefix="/statistics", tags=("statistics",)),
    "system": _RouterMount("app.api.system.router", prefix="/system", tags=("system",)),
    "system_shutdown": _RouterMount("app.api.system.shutdown", prefix="/system", tags=("system",)),
    "features": _RouterMount("app.api.features.router", prefix="/features", tags=("features",)),
    "tts": _RouterMount("app.api.tts.router", prefix="/tts", tags=("tts",)),
    "stt": _RouterMount("app.api.stt.router", prefix="/stt", tags=("stt",)),
    "voice": _RouterMount("app.api.voice.realtime", prefix="/voice", tags=("voice",)),
    "companion": _RouterMount("app.api.companion.router", prefix="/companion", tags=("companion",)),
    "client_logs": _RouterMount("app.api.client_logs", tags=("logs",)),
    "channels_login": _RouterMount("app.api.channels.login", prefix="/channels", tags=("channels",)),
    "channels_manage": _RouterMount("app.api.channels.router", prefix="/channels/manage", tags=("channels",)),
    "channels_test": _RouterMount("app.api.channels.test_connections", prefix="/channels/manage", tags=("channels",)),
    "channels_wechat": _RouterMount("app.api.channels.wechat", prefix="/channels/manage", tags=("channels",)),
    "feishu_register": _RouterMount("app.api.channels.feishu_register", prefix="/channels/manage", tags=("channels",)),
    "channels_instances": _RouterMount("app.api.channels.instances", prefix="/channels/manage", tags=("channels",)),
    "channels_topics": _RouterMount("app.api.channels.topics", prefix="/channels/manage", tags=("channels",)),
    "channels_routes": _RouterMount("app.api.channels.routes_management", prefix="/channels/routes", tags=("channels",)),
    "channels_dlq": _RouterMount("app.api.channels.dlq", prefix="/channels/dlq", tags=("channels",)),
    "api_keys": _RouterMount("app.api.api_keys", attr="router"),
    "media": _RouterMount("app.api.media", attr="media_router", prefix="/media", tags=("media",)),
    "budget": _RouterMount("app.api.budget", attr="budget_router", prefix="/budget", tags=("budget",)),
    "widget_storage": _RouterMount("app.api.widget_storage", tags=("widget-storage",)),
    "remote_access": _RouterMount("app.api.remote_access.router", prefix="/remote-access", tags=("remote-access",)),
}

PRESETS: dict[str, tuple[str, ...]] = {
    "chats": ("chats",),
    "health": ("health", "diagnostic"),
    "notifications": ("notifications",),
    "security": (
        "allowlist",
        "security_estop",
        "security_dashboard",
        "security_generate",
        "security_profiles",
        "vault",
        "vault_credentials",
    ),
    "integrations": ("integrations",),
    "channels_local": (
        "channels_login",
        "channels_manage",
        "channels_test",
        "channels_wechat",
        "feishu_register",
        "channels_instances",
        "channels_topics",
        "channels_routes",
        "channels_dlq",
    ),
    "evolution": ("evolution", "evolution_ws"),
    "files": ("files", "vault_proxy", "artifact_share_public"),
    "config": ("config", "artifact_mappings"),
    "statistics": ("statistics",),
    "memory": ("memory",),
    "projects": ("projects", "chats"),
    "wiki": ("wiki",),
    "connect": ("connect",),
    "companion": ("companion",),
    "client_logs": ("client_logs",),
    "features": ("features", "tts", "stt", "voice"),
    "eval": ("eval",),
    "workspace": ("workspace",),
    "system": ("system", "system_shutdown"),
    "cron": ("cron",),
    "external_agents": ("external_agents",),
    "openai_compat_only": ("api_keys",),
    "agents_api": (
        "agents_general",
        "agents_subagents",
        "agents_templates",
        "user_agents",
        "generate_prompt",
        "agent_history",
        "openapi_services",
        "fleet_overview",
        "goals",
        "memory",
        "wiki",
        "chats",
        "files",
    ),
    "skills_api": ("skills", "skill_growth", "skill_quality", "evolution", "experience_ledger", "migrations", "migration_discovery", "reviews"),
    "agent_with_skills": (
        "agents_general",
        "agents_subagents",
        "agents_templates",
        "user_agents",
        "generate_prompt",
        "agent_history",
        "openapi_services",
        "fleet_overview",
        "goals",
        "memory",
        "wiki",
        "chats",
        "files",
        "skills",
        "skill_quality",
    ),
    "migrations_api": ("migrations", "migration_discovery", "migration_upload", "skills", "memory"),
    "review_inbox": ("approvals", "skills", "evolution", "reviews", "migrations"),
    "webui_only": (),
}


def _resolve_router_keys(
    router_keys: Sequence[str],
    *,
    preset: str | None,
) -> tuple[str, ...]:
    if preset is not None:
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset {preset!r}; known: {sorted(PRESETS)}")
        base = PRESETS[preset]
        if router_keys:
            return (*base, *router_keys)
        return base
    return tuple(router_keys)


def build_minimal_app(
    *router_keys: str,
    preset: str | None = None,
    openai_compat: bool = False,
    mem0_compat: bool = False,
    webui: bool = False,
    include_health_check: bool = False,
    register_handlers: bool = True,
) -> FastAPI:
    """Return a FastAPI app with only the requested routers under ``settings.api_prefix``."""
    keys = _resolve_router_keys(router_keys, preset=preset)
    unknown = [k for k in keys if k not in _ROUTER_MOUNTS]
    if unknown:
        raise ValueError(f"Unknown router keys: {unknown}")

    app = FastAPI(title="Minimal Test App")
    api = APIRouter()
    for key in keys:
        _mount(api, _ROUTER_MOUNTS[key])
    app.include_router(api, prefix=API_PREFIX)

    if openai_compat:
        from app.api.openai_compat.router import openai_compat_router

        app.include_router(openai_compat_router)

    if mem0_compat:
        from app.api.mem0_compat.router import mem0_compat_router

        app.include_router(mem0_compat_router)

    if webui:
        from app.api.webui.router import router as webui_router

        app.include_router(webui_router)

    if include_health_check:

        @app.get("/health")
        async def _health_check() -> str:
            return "ok"

    if register_handlers:
        from app.core.utils.errors import register_exception_handlers
        from app.server.exceptions import general_exception_handler, not_found_handler

        app.add_exception_handler(404, not_found_handler)
        app.add_exception_handler(Exception, general_exception_handler)
        register_exception_handlers(app)

    return app


def preset_for_test_path(relative_path: str) -> str | None:
    """Map a test file path under ``tests/`` to a minimal-app preset name."""
    path = relative_path.replace("\\", "/")
    if path.startswith("tests/api/chats/"):
        return "chats"
    if path.startswith("tests/api/health/"):
        return "health"
    if path.startswith("tests/api/notifications/"):
        return "notifications"
    if path.startswith("tests/api/security/"):
        return "security"
    if path.startswith("tests/api/integrations/"):
        return "integrations"
    if path.startswith("tests/api/openai_compat/"):
        return "openai_compat_only"
    if path.startswith("tests/api/channels/"):
        return "channels_local"
    if path.startswith("tests/api/evolution/"):
        return "evolution"
    if path.startswith("tests/api/files/"):
        return "files"
    if path.startswith("tests/api/config/"):
        return "config"
    if path.startswith("tests/api/statistics/"):
        return "statistics"
    if path.startswith("tests/api/memory/"):
        return "memory"
    if path.startswith("tests/api/projects/"):
        return "projects"
    if path.startswith("tests/api/wiki/"):
        return "wiki"
    if path.startswith("tests/api/webui/"):
        return "webui_only"
    if path.startswith("tests/api/connect/"):
        return "connect"
    if path.startswith("tests/api/companion/"):
        return "companion"
    if path.startswith("tests/api/client_logs/") or path.startswith("tests/api/logs/"):
        return "client_logs"
    if path.startswith("tests/api/features/"):
        return "features"
    if path.startswith("tests/api/eval/test_workspace_isolation"):
        return "agent_with_skills"
    if path.startswith("tests/api/eval/"):
        return "eval"
    if path.startswith("tests/api/workspace_rules/"):
        return "workspace"
    if path.startswith("tests/api/agent/"):
        return "agents_api"
    if path.startswith("tests/architecture/"):
        return "integrations"
    if path.startswith("tests/services/webui/"):
        return "webui_only"
    if path.startswith("tests/services/memory/"):
        return "memory"
    if path == "tests/api/test_external_agents_auth.py":
        return "external_agents"
    if path == "tests/api/test_external_agents_install.py":
        return "external_agents"
    if path == "tests/api/test_experience_ledger.py":
        return "skills_api"
    if path == "tests/api/test_migration_import_dry_run_v14.py":
        return "migrations_api"
    if path == "tests/api/test_migrations_api.py":
        return "migrations_api"
    if path == "tests/api/test_conversation_formatter_e2e.py":
        return "chats"
    if path == "tests/api/test_review_inbox.py":
        return "review_inbox"
    if path == "tests/api/test_health_websocket_feature.py":
        return "health"
    if path.startswith("tests/e2e/test_public_ingress"):
        return "system"
    if path.startswith("tests/integration/test_top_sessions"):
        return "statistics"
    if path.startswith("tests/integration/test_activity_patterns"):
        return "statistics"
    if path.startswith("tests/integration/test_skill_quality"):
        return "skills_api"
    return None


def build_openai_compat_test_app() -> FastAPI:
    """OpenAI-compat routes plus API key management under ``/api/v1``."""
    return build_minimal_app("api_keys", openai_compat=True)


def build_minimal_app_for_test_path(relative_path: str) -> FastAPI:
    """Build a minimal app inferred from the test file location."""
    preset = preset_for_test_path(relative_path)
    if preset is None:
        raise ValueError(f"No preset mapping for test path: {relative_path}")
    if preset == "openai_compat_only":
        return build_minimal_app(preset=preset, openai_compat=True)
    if preset == "webui_only":
        return build_minimal_app(webui=True)
    return build_minimal_app(preset=preset)
