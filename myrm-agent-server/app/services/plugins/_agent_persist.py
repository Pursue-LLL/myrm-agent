"""Agent and team persistence for Agent Plugins 1.0.0 (business layer).

Persists ``PluginAgent`` records into ``AgentService`` as Agent profiles with
automatic subagent linking and safe template workspace files embedding.
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

__all__ = ["persist_imported_agents", "sanitize_imported_security_overrides"]

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

    # Pre-encode workspace files to text dict for metadata storage
    workspace_templates: dict[str, str] = {}
    for rel_path, content in session.plugin_result.workspace_files.items():
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
        created_agent_ids.append(new_sub.id)

    # Second pass: create entry agents with linked subagent_ids
    for _, agent in entry_list:
        linked_sub_ids: list[str] = [
            name_to_id[sa_name]
            for sa_name in agent.subagent_names
            if sa_name in name_to_id
        ]
        if not linked_sub_ids:
            linked_sub_ids = [sub_id for sub_id in name_to_id.values()]

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
