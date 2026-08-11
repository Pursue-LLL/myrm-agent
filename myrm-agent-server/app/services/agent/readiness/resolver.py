"""Per-agent readiness resolver — proactive config dry-run.

Checks 6 dimensions (model / mcp / skills / tools / search / deployment) against
a resolved agent profile and global user config. Returns a structured report with
ready / warning / blocked levels and settings deep-link paths. The mcp dimension
also preflights scoped secrets (``required_secrets`` + ``{{secret:KEY}}`` header
references) against the agent vault so missing credentials surface before runtime.

[INPUT]
- app.services.agent.profile.profile_resolver::AgentProfileResolver (POS: per-agent profile SSOT)
- app.core.channel_bridge.config_readiness::ProviderConfigChecker (POS: provider readiness)
- app.core.channel_bridge.config_loader::load_user_configs (POS: global user config)
- app.services.agent.backends.secret_backend::DatabaseSecretBackend (POS: agent secret vault)

[OUTPUT]
- ReadinessLevel: ready / warning / blocked
- AgentReadinessItem: single-dimension check result
- AgentReadinessReport: aggregated per-agent report
- _agent_settings_path: canonical deep-link to the agent editor tab on Settings
- _collect_bound_secret_keys: dedupe secret keys bound MCP servers depend on
- resolve_agent_readiness: async entry point
- get_readiness_resolver: global singleton accessor

[POS]
Business-layer per-agent readiness checking. Answers "is this agent ready to
execute?" before the user sends a message. Pure static config checks against
resolved agent profile and user config (zero LLM calls, zero network probes).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Sequence
from urllib.parse import quote

from app.services.agent.profile.profile_resolver import (
    ResolvedAgentProfile,
    get_agent_profile_resolver,
)

if TYPE_CHECKING:
    from app.core.types import MCPServerConfig

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300.0

_SECRET_REF_PATTERN = re.compile(r"\{\{secret:([^}]+)\}\}")


class ReadinessLevel(str, Enum):
    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AgentReadinessItem:
    """Single dimension check result."""

    dimension: str
    level: ReadinessLevel
    reason: str
    next_action: str
    settings_path: str


@dataclass(frozen=True, slots=True)
class AgentReadinessReport:
    """Aggregated per-agent readiness report."""

    overall_level: ReadinessLevel
    items: tuple[AgentReadinessItem, ...]
    agent_id: str
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_level": self.overall_level.value,
            "items": [
                {
                    "dimension": item.dimension,
                    "level": item.level.value,
                    "reason": item.reason,
                    "next_action": item.next_action,
                    "settings_path": item.settings_path,
                }
                for item in self.items
            ],
            "agent_id": self.agent_id,
            "checked_at": self.checked_at,
        }


def _aggregate_level(items: Sequence[AgentReadinessItem]) -> ReadinessLevel:
    """Compute overall level from individual items (worst wins)."""
    if any(i.level == ReadinessLevel.BLOCKED for i in items):
        return ReadinessLevel.BLOCKED
    if any(i.level == ReadinessLevel.WARNING for i in items):
        return ReadinessLevel.WARNING
    return ReadinessLevel.READY


def _agent_settings_path(agent_id: str, anchor: str = "loadout") -> str:
    """Deep-link to the agent editor tab on the Settings page.

    Mirrors the frontend ``agentSettingsHref`` (loadoutDeepLinks.ts) so the
    readiness badge and the agent editor agree on the same canonical route.
    """
    return f"/settings/agents?agentId={quote(agent_id, safe='')}#{anchor}"


def _check_model(
    profile: ResolvedAgentProfile,
    providers_dict: dict[str, object] | None,
) -> AgentReadinessItem | None:
    """Check if the agent's model provider is configured and has valid keys."""
    from app.core.channel_bridge.config_readiness import ProviderConfigChecker

    result = ProviderConfigChecker().check(providers_dict)
    if result.is_ready:
        return None
    return AgentReadinessItem(
        dimension="model",
        level=ReadinessLevel.BLOCKED,
        reason=(
            result.missing_items[0]
            if result.missing_items
            else "provider_not_configured"
        ),
        next_action=(
            result.suggestions[0] if result.suggestions else "Configure model provider"
        ),
        settings_path="/settings/models",
    )


def _collect_bound_secret_keys(servers: Sequence["MCPServerConfig"]) -> list[str]:
    """Collect secret keys bound MCP servers depend on (env + header references).

    ``required_secrets`` declares the scoped env keys; ``{{secret:KEY}}`` header
    references are resolved at connection time by ``MCPSecretAuthProvider``. Both
    must exist in the agent vault for the server to authenticate.
    """
    keys: list[str] = []
    for server in servers:
        for key in server.required_secrets or []:
            stripped = key.strip()
            if stripped:
                keys.append(stripped)
        for value in (server.headers or {}).values():
            keys.extend(_SECRET_REF_PATTERN.findall(value))
    return list(dict.fromkeys(key.strip() for key in keys if key.strip()))


async def _check_mcp(
    profile: ResolvedAgentProfile,
    mcp_dict: dict[str, object] | None,
    org_mcp_dict: dict[str, object] | None = None,
) -> list[AgentReadinessItem]:
    """Check bound MCP servers exist in config and their secrets are configured.

    The configured set covers both user-managed servers (``mcp_dict``) and
    org-managed servers pushed by the Control Plane (``org_mcp_dict``), matching
    the runtime merge via config_parsers.merge_org_mcp_configs so the report
    agrees with actual execution.
    """
    if not profile.mcp_ids:
        return []

    from app.core.channel_bridge.config_parsers import (
        extract_mcp_configs,
        merge_org_mcp_configs,
    )

    configured: dict[str, MCPServerConfig] = {
        cfg.name: cfg
        for cfg in merge_org_mcp_configs(
            extract_mcp_configs(mcp_dict),
            org_mcp_dict,
        )
    }

    items: list[AgentReadinessItem] = []
    missing = [mid for mid in profile.mcp_ids if mid not in configured]
    if missing:
        items.append(
            AgentReadinessItem(
                dimension="mcp",
                level=ReadinessLevel.WARNING,
                reason=f"{len(missing)} MCP server(s) not found in config",
                next_action=f"Check MCP configuration for: {', '.join(missing[:3])}",
                settings_path="/settings/mcp",
            )
        )

    bound = [configured[mid] for mid in profile.mcp_ids if mid in configured]
    required_keys = _collect_bound_secret_keys(bound)
    if required_keys:
        try:
            from app.services.agent.backends.secret_backend import DatabaseSecretBackend

            existing = set(
                await DatabaseSecretBackend().list_secret_keys(profile.agent_id)
            )
            missing_keys = [key for key in required_keys if key not in existing]
            if missing_keys:
                items.append(
                    AgentReadinessItem(
                        dimension="mcp",
                        level=ReadinessLevel.WARNING,
                        reason=f"MCP servers missing secrets: {', '.join(missing_keys[:3])}",
                        next_action="Add the missing secrets in agent settings",
                        settings_path=_agent_settings_path(
                            profile.agent_id, anchor="secrets"
                        ),
                    )
                )
        except Exception as exc:
            logger.debug("MCP secret preflight skipped: %s", exc)
    return items


def _check_skills(profile: ResolvedAgentProfile) -> list[AgentReadinessItem]:
    """Check if bound skills exist in the skill store."""
    if not profile.skill_ids:
        return []

    items: list[AgentReadinessItem] = []
    try:
        from app.services.skills.evolution_review.disk import get_skill_store

        store = get_skill_store()
        missing = [sid for sid in profile.skill_ids if store.get_skill(sid) is None]
        if missing:
            items.append(
                AgentReadinessItem(
                    dimension="skills",
                    level=ReadinessLevel.WARNING,
                    reason=f"{len(missing)} skill(s) not found: {', '.join(missing[:3])}",
                    next_action="Remove or replace missing skills in agent settings",
                    settings_path=_agent_settings_path(profile.agent_id),
                )
            )
    except Exception as exc:
        logger.debug("Skill check skipped: %s", exc)
    return items


def _check_tools(profile: ResolvedAgentProfile) -> list[AgentReadinessItem]:
    """Check tool enablement and deployment compatibility."""
    items: list[AgentReadinessItem] = []
    if not profile.enabled_builtin_tools:
        items.append(
            AgentReadinessItem(
                dimension="tools",
                level=ReadinessLevel.WARNING,
                reason="No built-in tools enabled",
                next_action="Enable at least one tool in agent settings",
                settings_path=_agent_settings_path(profile.agent_id),
            )
        )
    return items


def _check_search(
    search_is_user_configured: bool,
) -> AgentReadinessItem | None:
    """Check search service configuration."""
    if search_is_user_configured:
        return None
    return AgentReadinessItem(
        dimension="search",
        level=ReadinessLevel.WARNING,
        reason="No search service configured",
        next_action="Enable SearXNG or add a search provider in Settings",
        settings_path="/settings/search",
    )


def _check_deployment(profile: ResolvedAgentProfile) -> list[AgentReadinessItem]:
    """Check deployment-specific constraints (cloud sandbox / Tauri / local)."""
    items: list[AgentReadinessItem] = []
    try:
        from app.platform_utils.deployment_capabilities import (
            get_deployment_capabilities,
        )

        caps = get_deployment_capabilities()

        if (
            "computer_use" in set(profile.enabled_builtin_tools)
            and caps.is_sandbox_instance
        ):
            items.append(
                AgentReadinessItem(
                    dimension="deployment",
                    level=ReadinessLevel.WARNING,
                    reason="Computer Use may have limited capabilities in sandbox",
                    next_action="Verify browser tools are available in sandbox",
                    settings_path=_agent_settings_path(profile.agent_id),
                )
            )
        if not caps.allows_local_skills and profile.skill_ids:
            items.append(
                AgentReadinessItem(
                    dimension="deployment",
                    level=ReadinessLevel.WARNING,
                    reason="Local skills not available in current deployment",
                    next_action="Use prebuilt or marketplace skills instead",
                    settings_path=_agent_settings_path(profile.agent_id),
                )
            )
    except Exception as exc:
        logger.debug("Deployment check skipped: %s", exc)
    return items


async def resolve_agent_readiness(agent_id: str) -> AgentReadinessReport:
    """Resolve per-agent readiness report.

    Checks all 6 dimensions: model, mcp, skills, tools, search, deployment.
    Returns structured report with overall level + per-item details.
    """
    from app.core.channel_bridge.config_loader import load_user_configs

    resolver = get_agent_profile_resolver()
    profile = await resolver.resolve(agent_id)

    if profile is None:
        return AgentReadinessReport(
            overall_level=ReadinessLevel.BLOCKED,
            items=(
                AgentReadinessItem(
                    dimension="model",
                    level=ReadinessLevel.BLOCKED,
                    reason="Agent not found",
                    next_action="Check agent ID or create a new agent",
                    settings_path="/settings/agents",
                ),
            ),
            agent_id=agent_id,
        )

    try:
        configs = await asyncio.wait_for(load_user_configs(), timeout=3.0)
    except Exception:
        configs = None

    providers_dict = configs.providers_dict if configs else None
    mcp_dict = configs.mcp_dict if configs else None
    org_mcp_dict = configs.org_mcp_dict if configs else None
    search_configured = bool(configs and configs.search_is_user_configured)

    items: list[AgentReadinessItem] = []

    model_item = _check_model(profile, providers_dict)
    if model_item is not None:
        items.append(model_item)

    items.extend(await _check_mcp(profile, mcp_dict, org_mcp_dict))

    items.extend(_check_skills(profile))
    items.extend(_check_tools(profile))

    search_item = _check_search(search_configured)
    if search_item is not None:
        items.append(search_item)

    items.extend(_check_deployment(profile))

    overall = _aggregate_level(items) if items else ReadinessLevel.READY
    return AgentReadinessReport(
        overall_level=overall,
        items=tuple(items),
        agent_id=agent_id,
    )


class _ReadinessResolverCache:
    """Simple TTL cache for readiness reports."""

    __slots__ = ("_cache",)

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, AgentReadinessReport]] = {}

    async def resolve(self, agent_id: str) -> AgentReadinessReport:
        now = time.monotonic()
        cached = self._cache.get(agent_id)
        if cached is not None:
            ts, report = cached
            if now - ts < _CACHE_TTL_SECONDS:
                return report
        report = await resolve_agent_readiness(agent_id)
        self._cache[agent_id] = (now, report)
        return report

    def invalidate(self, agent_id: str) -> None:
        self._cache.pop(agent_id, None)

    def invalidate_all(self) -> None:
        self._cache.clear()


_resolver_cache: _ReadinessResolverCache | None = None


def get_readiness_resolver() -> _ReadinessResolverCache:
    """Return the global readiness resolver singleton."""
    global _resolver_cache
    if _resolver_cache is None:
        _resolver_cache = _ReadinessResolverCache()
    return _resolver_cache
