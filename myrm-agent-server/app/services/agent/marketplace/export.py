"""Marketplace export — serialize Agent profile with bundled dependencies.

Produces a portable JSON package containing the Agent configuration plus all
custom Skill definitions (with resources), MCP configurations, and Subagent
profiles required for cross-sandbox installation. Secrets are always stripped.

[INPUT]
- database.repositories.uow::UnitOfWork (POS: Unit of Work 事务层)
- core.skills.store.service::skills_service (POS: Skill CRUD 单例服务)
- services.agent.profile_snapshot_service::mutable_snapshot_data (POS: Agent 字段序列化)
- services.agent.marketplace.package_contract::build_marketplace_package
  (POS: Marketplace 包契约构建 + 完整性摘要)

[OUTPUT]
- export_agent_package(uow, agent_id): Contract-compliant marketplace package dict

[POS]
Server-side export for marketplace publish flow. Strips secrets, bundles
custom dependencies (Skill content + resources + MCP + Subagent), produces
a self-contained JSON package for cross-sandbox distribution.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.core.skills.store.service import skills_service
from app.database.repositories.uow import UnitOfWork
from app.services.agent.marketplace.package_contract import build_marketplace_package
from app.services.agent.profile_snapshot_service import mutable_snapshot_data

logger = logging.getLogger(__name__)

_SENSITIVE_FIELDS = frozenset({
    "api_key", "auth_token", "secret", "password", "token",
    "credentials", "private_key",
})


def _strip_sensitive(data: dict) -> dict:
    """Recursively strip sensitive fields from a dict."""
    cleaned: dict = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_FIELDS:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_sensitive(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _strip_sensitive(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


async def export_agent_package(uow: UnitOfWork, agent_id: str) -> dict:
    """Export an Agent profile as a marketplace-ready package.

    Matches the API-layer call: export_agent_package(uow, agent_id).

    Raises:
        ValueError: If agent_id not found.
    """
    agent_profile = await uow.agent_repo.get_profile(agent_id)
    if not agent_profile:
        raise ValueError(f"Agent '{agent_id}' not found")

    snapshot = mutable_snapshot_data(agent_profile)
    snapshot = _strip_sensitive(snapshot)

    bundled_skills = await _bundle_custom_skills(agent_profile)
    bundled_mcp_configs = _bundle_mcp_configs(agent_profile)
    bundled_subagents = await _bundle_subagents(uow, agent_profile)

    return build_marketplace_package(
        agent_profile=snapshot,
        bundled_skills=bundled_skills,
        bundled_mcp_configs=bundled_mcp_configs,
        bundled_subagents=bundled_subagents,
    )


async def _bundle_custom_skills(profile: AgentProfile) -> list[dict]:
    """Bundle custom (non-builtin) Skill definitions with content and resources."""
    skill_ids: list[str] = profile.skills or []
    if not skill_ids:
        return []

    skills = await skills_service.get_skills_by_ids(skill_ids)

    bundled: list[dict] = []
    for skill in skills:
        if skill.type.value == "prebuilt":
            continue

        skill_data: dict = {
            "name": skill.name,
            "description": skill.description,
            "id": skill.id,
        }

        try:
            content = await skills_service.get_skill_file(skill.id, "SKILL.md")
            if content:
                skill_data["content"] = content.decode("utf-8", errors="replace")
            else:
                logger.warning("No SKILL.md for skill '%s', skipping", skill.name)
                continue
        except Exception:
            logger.warning("Failed to get content for skill '%s'", skill.name)
            continue

        try:
            file_list = await skills_service.list_skill_files(skill.id)
            resources: dict[str, str] = {}
            for fpath in file_list:
                if fpath == "SKILL.md":
                    continue
                try:
                    data = await skills_service.get_skill_file(skill.id, fpath)
                    if data:
                        resources[fpath] = data.decode("utf-8", errors="replace")
                except Exception:
                    logger.debug("Skipping resource '%s/%s'", skill.name, fpath)
            if resources:
                skill_data["resources"] = resources
        except Exception:
            logger.debug("No resource listing for skill '%s'", skill.name)

        bundled.append(skill_data)

    return bundled


def _bundle_mcp_configs(profile: AgentProfile) -> list[dict]:
    """Bundle MCP server configurations, stripping credentials."""
    metadata = profile.metadata or {}
    mcp_ids = metadata.get("mcp_ids")
    if not isinstance(mcp_ids, list) or not mcp_ids:
        return []

    mcp_tool_selections = metadata.get("mcp_tool_selections")
    configs: list[dict] = []
    for mcp_id in mcp_ids:
        config: dict = {"original_id": str(mcp_id)}
        if isinstance(mcp_tool_selections, dict):
            selections = mcp_tool_selections.get(str(mcp_id))
            if selections:
                config["tool_selections"] = selections
        configs.append(config)

    return configs


async def _bundle_subagents(uow: UnitOfWork, profile: AgentProfile) -> list[dict]:
    """Bundle first-level Subagent profiles (non-recursive)."""
    metadata = profile.metadata or {}
    subagent_ids = metadata.get("subagent_ids")
    if not isinstance(subagent_ids, list) or not subagent_ids:
        return []

    bundled: list[dict] = []
    for sub_id in subagent_ids:
        sub_profile = await uow.agent_repo.get_profile(str(sub_id))
        if not sub_profile:
            logger.warning("Subagent '%s' not found, skipping", sub_id)
            continue
        sub_snapshot = mutable_snapshot_data(sub_profile)
        sub_snapshot = _strip_sensitive(sub_snapshot)
        bundled.append({
            "original_id": sub_profile.id,
            "profile": sub_snapshot,
        })

    return bundled
