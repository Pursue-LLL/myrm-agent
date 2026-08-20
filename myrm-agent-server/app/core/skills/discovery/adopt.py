"""Discover adoption: append installed skills to explicit agent allowlists.

[INPUT]
- app.services.agent.agent_service::AgentService (POS: Agent CRUD)
- app.core.skills.effective_skill_ids::normalize_local_skill_id (POS: Skill ID normalization)
- app.core.skills.store.service::skills_service (POS: User skill config)

[OUTPUT]
- complete_discovery_adoption: After catalog enable, append skill to explicit allowlist

[POS]
Discovery install adoption bridge. When the user installs with mount_to_agent and the target
agent already uses a non-empty skill_ids allowlist, append the new catalog skill so the
next chat turn can load it without opening Agent Editor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.skills.effective_skill_ids import (
    _legacy_install_roots,
    normalize_local_skill_id,
)
from app.core.skills.store.service import skills_service
from app.database.dto import AgentUpdate
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveryAdoptionResult:
    allowlist_appended: bool = False
    agent_id: str = ""
    allowlist_append_error: str = ""


def _profile_explicit_skill_ids(agent: object) -> list[str]:
    raw = getattr(agent, "skill_ids", None) or getattr(agent, "skills", None) or []
    return [sid.strip() for sid in raw if isinstance(sid, str) and sid.strip()]


async def complete_discovery_adoption(
    agent_id: str,
    catalog_skill_id: str,
) -> DiscoveryAdoptionResult:
    """Append catalog_skill_id when the agent profile uses a non-empty explicit allowlist."""
    context_agent_id = agent_id.strip()
    skill_id = catalog_skill_id.strip()
    if not context_agent_id or not skill_id:
        return DiscoveryAdoptionResult()

    agent = await AgentService.get_agent_by_id(context_agent_id)
    if agent is None:
        return DiscoveryAdoptionResult()

    existing = _profile_explicit_skill_ids(agent)
    if not existing:
        return DiscoveryAdoptionResult()

    config = await skills_service.user_config.get_config()
    install_roots = _legacy_install_roots(config.local_skill_paths)
    normalized_new = normalize_local_skill_id(skill_id, install_roots)
    normalized_existing = {normalize_local_skill_id(sid, install_roots) for sid in existing}
    if normalized_new in normalized_existing:
        return DiscoveryAdoptionResult()

    merged: list[str] = []
    seen: set[str] = set()
    for candidate in [*existing, skill_id]:
        normalized = normalize_local_skill_id(candidate, install_roots)
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(candidate)

    outcome = await AgentService.update_agent(
        context_agent_id,
        AgentUpdate(skill_ids=merged),
    )
    if outcome is None:
        logger.warning(
            "Failed to append skill %s to agent %s allowlist after discovery adoption",
            normalized_new,
            context_agent_id,
        )
        return DiscoveryAdoptionResult(
            allowlist_append_error=("Failed to update agent skill allowlist after install"),
        )

    logger.info(
        "Appended skill %s to agent %s allowlist after discovery adoption",
        normalized_new,
        context_agent_id,
    )
    return DiscoveryAdoptionResult(
        allowlist_appended=True,
        agent_id=context_agent_id,
    )


async def remove_skill_from_all_agents(
    catalog_skill_id: str,
) -> int:
    """Remove a skill ID from all Agent profiles' explicit allowlists (orphan cleanup)."""
    skill_id = catalog_skill_id.strip()
    if not skill_id:
        return 0

    config = await skills_service.user_config.get_config()
    install_roots = _legacy_install_roots(config.local_skill_paths)
    target_canonical = normalize_local_skill_id(skill_id, install_roots)

    agents = await AgentService.get_all_agents()
    cleaned_count = 0

    for agent in agents:
        existing = _profile_explicit_skill_ids(agent)
        if not existing:
            continue

        retained: list[str] = []
        changed = False
        for sid in existing:
            if normalize_local_skill_id(sid, install_roots) == target_canonical:
                changed = True
            else:
                retained.append(sid)

        if changed:
            outcome = await AgentService.update_agent(
                agent.id,
                AgentUpdate(skill_ids=retained),
            )
            if outcome is not None:
                cleaned_count += 1
                logger.info(
                    "Cleaned uninstalled skill %s from agent %s allowlist",
                    target_canonical,
                    agent.id,
                )

    return cleaned_count


async def sync_skill_to_agents(
    catalog_skill_id: str,
    target_agent_ids: list[str],
) -> dict[str, bool]:
    """Sync a skill ID into multiple Agent profiles' explicit allowlists."""
    skill_id = catalog_skill_id.strip()
    if not skill_id or not target_agent_ids:
        return {}

    config = await skills_service.user_config.get_config()
    install_roots = _legacy_install_roots(config.local_skill_paths)
    normalized_new = normalize_local_skill_id(skill_id, install_roots)

    results: dict[str, bool] = {}
    for agent_id in target_agent_ids:
        agent = await AgentService.get_agent_by_id(agent_id.strip())
        if agent is None:
            results[agent_id] = False
            continue

        existing = _profile_explicit_skill_ids(agent)
        normalized_existing = {normalize_local_skill_id(sid, install_roots) for sid in existing}
        if normalized_new in normalized_existing:
            results[agent_id] = True
            continue

        merged: list[str] = [*existing, skill_id]
        outcome = await AgentService.update_agent(
            agent_id.strip(),
            AgentUpdate(skill_ids=merged),
        )
        results[agent_id] = outcome is not None

    return results
