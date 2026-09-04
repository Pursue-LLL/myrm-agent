"""Agent and team persistence for Agent Plugins 1.0.0 (business layer).

Persists ``PluginAgent`` records into ``AgentService`` as Agent profiles with
automatic subagent linking and safe template workspace files embedding.

[INPUT]
- ._models::PluginImportSession, PluginConfirmItem (POS: plugin import DTOs.)
- myrm_agent_harness.agent.plugins.models::PluginAgent (POS: parsed plugin agent dataclass.)
- app.database.dto::AgentCreate (POS: DTO for creating new Agent profiles.)
- app.services.agent.agent_service::AgentService (POS: business service for managing agent profiles.)

[OUTPUT]
- persist_imported_agents: persist selected PluginAgent entries into Agent profiles with subagent linking.
- sanitize_imported_security_overrides: strip dangerous permission overrides from imported profiles.

[POS]
Business-layer persistence helper for imported plugin agents and subagent team hierarchies.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from app.database.dto import AgentCreate
from app.services.agent.agent_service import AgentService

if TYPE_CHECKING:
    from myrm_agent_harness.agent.plugins.models import PluginAgent

    from ._models import PluginConfirmItem, PluginImportSession

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_TEMPLATE_FILE_BYTES",
    "MAX_TOTAL_TEMPLATE_BYTES",
    "persist_imported_agents",
    "sanitize_imported_security_overrides",
]

# Maximum size allowed for a single template workspace file (1MB)
MAX_TEMPLATE_FILE_BYTES: int = 1 * 1024 * 1024
# Maximum cumulative size allowed for all template workspace files in an agent (5MB)
MAX_TOTAL_TEMPLATE_BYTES: int = 5 * 1024 * 1024

# Restricted security permission keys that untrusted imported profiles cannot override
_DISALLOWED_SECURITY_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "required_permissions",
        "dangerously_skip_permissions",
        "bypass_sandbox",
        "host_execution_allowed",
        "system_sandbox_override",
    }
)


def sanitize_imported_security_overrides(
    metadata: dict[str, object],
) -> dict[str, object]:
    """Sanitize imported agent metadata to fail-closed against permission escalation."""
    sanitized: dict[str, object] = {}
    for key, val in metadata.items():
        if key.lower() in _DISALLOWED_SECURITY_OVERRIDE_KEYS:
            logger.warning(
                "Filtered disallowed security override key %r from imported agent metadata",
                key,
            )
            continue
        sanitized[key] = val
    return sanitized


async def persist_imported_agents(
    session: PluginImportSession,
    agent_decisions: list[PluginConfirmItem],
    *,
    skill_ids: list[str],
    mcp_names: list[str],
) -> tuple[list[str], int]:
    """Persist imported PluginAgent records into AgentService as Agent profiles with subagent linking."""
    decisions_by_virtual_id = {d.virtual_id: d for d in agent_decisions}
    accepted_agents: list[tuple[str, PluginAgent]] = []
    skipped = 0

    for virtual_id, agent in session.agents_by_key.items():
        decision = decisions_by_virtual_id.get(virtual_id)
        if decision and decision.resolution == "skip":
            skipped += 1
            continue
        accepted_agents.append((virtual_id, agent))

    if not accepted_agents:
        return [], skipped

    # Pre-encode workspace files to text dict for metadata storage with capacity guards
    workspace_templates: dict[str, str] = {}
    total_bytes = 0
    for rel_path, content in session.plugin_result.workspace_files.items():
        file_len = len(content)
        if file_len > MAX_TEMPLATE_FILE_BYTES:
            logger.warning(
                "Skipping oversized template file %r (%d bytes, max limit %d bytes)",
                rel_path,
                file_len,
                MAX_TEMPLATE_FILE_BYTES,
            )
            continue
        if total_bytes + file_len > MAX_TOTAL_TEMPLATE_BYTES:
            logger.warning(
                "Skipping template file %r: total workspace template files size exceeds limit (%d bytes, max %d bytes)",
                rel_path,
                total_bytes + file_len,
                MAX_TOTAL_TEMPLATE_BYTES,
            )
            break
        total_bytes += file_len
        try:
            workspace_templates[rel_path] = content.decode("utf-8")
        except Exception:
            workspace_templates[rel_path] = (
                f"base64:{base64.b64encode(content).decode('ascii')}"
            )

    # First pass: create subagents
    created_agent_ids: list[str] = []
    name_to_id: dict[str, str] = {}

    subagent_list = [
        item
        for item in accepted_agents
        if item[1].is_subagent or not item[1].is_entry_agent
    ]
    entry_list = [
        item
        for item in accepted_agents
        if item[1].is_entry_agent or (item not in subagent_list)
    ]

    # If all were categorized as subagents but there's at least one, elevate the first to entry
    if not entry_list and subagent_list:
        entry_list = [subagent_list.pop(0)]

    for _, agent in subagent_list:
        payload: dict[str, object] = {
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "skill_ids": list(skill_ids),
            "mcp_ids": list(mcp_names),
            "max_iterations": agent.max_iterations,
            "agent_type": "individual",
            "is_built_in": False,
        }
        if agent.metadata:
            payload["metadata"] = sanitize_imported_security_overrides(
                dict(agent.metadata)
            )
        agent_data = AgentCreate.model_validate(payload)
        new_sub = await AgentService.create_agent(agent_data)
        name_to_id[agent.name] = new_sub.id
        name_to_id[agent.name.lower()] = new_sub.id
        if agent.metadata.get("slug"):
            slug_key = str(agent.metadata["slug"])
            name_to_id[slug_key] = new_sub.id
            name_to_id[slug_key.lower()] = new_sub.id
        created_agent_ids.append(new_sub.id)

    # Second pass: create entry agents with linked subagent_ids
    for _, agent in entry_list:
        linked_sub_ids: list[str] = []
        if agent.subagent_names:
            for sa_name in agent.subagent_names:
                normalized = sa_name.strip()
                sub_id = name_to_id.get(normalized) or name_to_id.get(normalized.lower())
                if sub_id and sub_id not in linked_sub_ids:
                    linked_sub_ids.append(sub_id)
        elif subagent_list and agent.is_entry_agent:
            # Fallback for implicit multi-agent team packages: if entry agent declared no explicit subagents,
            # bind all created subagents from the package.
            seen_ids: set[str] = set()
            for sub_id in name_to_id.values():
                if sub_id not in seen_ids:
                    seen_ids.add(sub_id)
                    linked_sub_ids.append(sub_id)

        payload = {
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "skill_ids": list(skill_ids),
            "mcp_ids": list(mcp_names),
            "subagent_ids": linked_sub_ids,
            "max_iterations": agent.max_iterations,
            "is_built_in": False,
        }
        if agent.metadata:
            payload["metadata"] = sanitize_imported_security_overrides(
                dict(agent.metadata)
            )
        if workspace_templates:
            payload["engine_params"] = {"template_workspace_files": workspace_templates}

        agent_data = AgentCreate.model_validate(payload)
        new_main = await AgentService.create_agent(agent_data)
        name_to_id[agent.name] = new_main.id
        created_agent_ids.append(new_main.id)

    return created_agent_ids, skipped
