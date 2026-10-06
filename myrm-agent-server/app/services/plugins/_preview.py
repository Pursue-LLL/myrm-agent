"""Preview serialization for Agent Plugins 1.0.0 (business layer).

Builds the preview payload of an uploaded plugin package: component cards with the
same conflict / block / unresolved-reference facts that confirm acts on, risk level
and capability diff, and package diagnostics.

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginParseResult, PluginSkill, PluginMcpServer, PluginAgent
  (POS: parsed plugin models.)
- ._gates (POS: shared pre-install gates: content scan, size, deployment blocks.)
- ._preview_context::PreviewContext (POS: installed skills, connectors, experts and deployment limits.)
- .agent_surface::import_agent_fields (POS: what an imported expert is granted.)
- .template_workspace::encode_template_files (POS: workspace template capacity diagnostics.)

[OUTPUT]
- build_preview_result: structured preview dictionary for the plugin import wizard.
- compute_capability_diff: capability changes against the installed version of the plugin.

[POS]
Business-layer preview builder for uploaded agent plugin archives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import _gates
from ._preview_context import PreviewContext, expert_key
from .agent_surface import import_agent_fields
from .template_workspace import OVERSIZED_FILE, encode_template_files

if TYPE_CHECKING:
    from myrm_agent_harness.agent.plugins.models import (
        PluginAgent,
        PluginMcpServer,
        PluginParseResult,
        PluginSkill,
    )

__all__ = ["build_preview_result", "compute_capability_diff"]


def _server_has_placeholders(server: PluginMcpServer) -> bool:
    from myrm_agent_harness.agent.plugins.mcp_config import has_placeholders

    values: list[str | None] = [server.cwd]
    if server.args:
        values.extend(server.args)
    values.extend(server.raw_env.values())
    return has_placeholders(*values)


def _preview_skill(idx: int, skill: PluginSkill, context: PreviewContext) -> dict[str, object]:
    """Serialize one skill for the preview payload."""
    blocked = _gates.skill_block_reason(skill, allows_local_skills=context.allows_local_skills)
    return {
        "name": skill.name,
        "description": skill.description,
        "file_count": len(skill.files),
        "virtual_id": f"skill:{idx}",
        # A blocked skill can never be installed; skip the content scan so the
        # preview mirrors confirm-time behavior instead of doing wasted work.
        "security_issues": [] if blocked else _gates.scan_skill_security(skill),
        "oversized_content": blocked == _gates.BLOCK_OVERSIZED,
        "blocked_reason": blocked,
        "conflict": skill.name.lower() in context.local_skill_names,
    }


def _preview_server(idx: int, server: PluginMcpServer, context: PreviewContext) -> dict[str, object]:
    return {
        "name": server.name,
        "type": server.server_type,
        "command": server.command,
        "url": server.url,
        "env_key_count": len(server.env_key_names),
        "has_placeholders": _server_has_placeholders(server),
        "virtual_id": f"mcp:{idx}",
        "missing_artifact": server.missing_artifact,
        "is_runnable": server.is_runnable,
        "missing_artifacts": list(server.missing_artifacts),
        "capabilities": [c.value for c in server.capabilities],
        "blocked_reason": _gates.server_block_reason(server, allow_stdio=context.allow_stdio),
    }


def _preview_agent(idx: int, agent: PluginAgent, result: PluginParseResult, context: PreviewContext) -> dict[str, object]:
    """Serialize one expert: what it would be granted and which references would not resolve."""
    imported = import_agent_fields(agent)
    existing = context.experts_by_name.get(expert_key(agent.name))
    bundled_skills = {skill.name.lower() for skill in result.skills}
    bundled_servers = {server.name for server in result.servers}
    package_experts = {expert_key(a.name) for a in result.agents} | {
        expert_key(str(a.metadata["slug"])) for a in result.agents if a.metadata.get("slug")
    }
    return {
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "max_iterations": agent.max_iterations,
        "effective_max_iterations": imported.fields.get("max_iterations"),
        "skill_names": list(agent.skill_names),
        "tool_names": list(agent.tool_names),
        "granted_tools": list(imported.granted_tools),
        "withheld_tools": list(imported.withheld_tools),
        "mcp_names": list(agent.mcp_names),
        "subagent_names": list(agent.subagent_names),
        "is_subagent": agent.is_subagent,
        "is_entry_agent": agent.is_entry_agent,
        "virtual_id": f"agent:{idx}",
        "conflict": existing is not None,
        "existing_agent_id": existing.agent_id if existing is not None else None,
        "existing_is_built_in": existing.is_built_in if existing is not None else False,
        "unresolved_skills": [
            n
            for n in agent.skill_names
            if n.strip().lower() not in bundled_skills and n.strip().lower() not in context.skill_ids_by_name
        ],
        "unresolved_connectors": [n for n in agent.mcp_names if n not in bundled_servers and n not in context.server_names],
        "unresolved_subagents": [
            n for n in agent.subagent_names if expert_key(n) not in package_experts or expert_key(n) == expert_key(agent.name)
        ],
    }


def _template_diagnostics(result: PluginParseResult) -> list[dict[str, object]]:
    """Warn about workspace template files that confirm will skip (capacity ceilings)."""
    from myrm_agent_harness.agent.plugins.rules import MAX_TEMPLATE_FILE_BYTES, MAX_TOTAL_TEMPLATE_BYTES

    diagnostics: list[dict[str, object]] = []
    for rel_path, reason in encode_template_files(result.workspace_files).skipped:
        if reason == OVERSIZED_FILE:
            code = "OVERSIZED_TEMPLATE_FILE"
            message = (
                f"Workspace template file '{rel_path}' ({len(result.workspace_files[rel_path])} bytes) "
                f"exceeds 1MB limit ({MAX_TEMPLATE_FILE_BYTES} bytes) and will be skipped"
            )
        else:
            code = "OVERSIZED_WORKSPACE_TOTAL"
            message = (
                f"Workspace template file '{rel_path}' exceeds cumulative 5MB limit "
                f"({MAX_TOTAL_TEMPLATE_BYTES} bytes) and will be skipped"
            )
        diagnostics.append({"component": f"workspace:{rel_path}", "code": code, "message": message, "level": "warning"})
    return diagnostics


def compute_capability_diff(
    old_capabilities: set[str],
    new_capabilities: set[str],
) -> dict[str, object]:
    """Compute difference between installed capabilities and new package capabilities.

    Identifies escalated privileges (e.g. adding shell_exec or destructive) to alert users.
    """
    added = sorted(new_capabilities - old_capabilities)
    removed = sorted(old_capabilities - new_capabilities)
    has_escalation = any(cap in ("shell_exec", "destructive") for cap in added) or (
        ("network" in added or "fs_write" in added)
        and not ("shell_exec" in old_capabilities or "destructive" in old_capabilities)
    )
    return {
        "added": added,
        "removed": removed,
        "has_escalation": has_escalation,
    }


def build_preview_result(
    result: PluginParseResult,
    context: PreviewContext | None = None,
    installed_capabilities: set[str] | None = None,
) -> dict[str, object]:
    """Serialize a parse result into the preview response payload.

    ``context`` carries the installation state (same-name skills and experts,
    configured connectors, deployment limits) so the UI can offer replace/skip
    and show what confirm would block; without it nothing conflicts or is blocked.
    """
    meta = result.meta
    context = context or PreviewContext()

    diagnostics_list: list[dict[str, object]] = [
        {
            "component": d.component,
            "code": d.code,
            "message": d.message,
            "level": d.level.value,
        }
        for d in result.diagnostics
    ]
    diagnostics_list.extend(_template_diagnostics(result))

    # Calculate effective capabilities and risk level
    aggregated_caps = [c.value for c in result.aggregated_capabilities]
    if "destructive" in aggregated_caps:
        risk_level = "critical"
        effective_tier = "destructive"
    elif "shell_exec" in aggregated_caps:
        risk_level = "high"
        effective_tier = "shell_exec"
    elif "network" in aggregated_caps or "fs_write" in aggregated_caps:
        risk_level = "medium"
        effective_tier = "network" if "network" in aggregated_caps else "fs_write"
    elif "fs_read" in aggregated_caps:
        risk_level = "low"
        effective_tier = "fs_read"
    else:
        risk_level = "low"
        effective_tier = "read_only"

    capability_diff = None
    if installed_capabilities is not None:
        capability_diff = compute_capability_diff(
            installed_capabilities,
            set(aggregated_caps),
        )

    # Check for undeclared privilege escalation between declared and inferred
    declared_set = {c.value for c in getattr(meta, "declared_capabilities", ())}
    if declared_set and not set(aggregated_caps).issubset(declared_set):
        undeclared = sorted(set(aggregated_caps) - declared_set)
        diagnostics_list.append(
            {
                "component": f"plugin:{meta.name if meta else 'manifest'}",
                "code": "capability_undeclared_privilege",
                "message": f"Plugin requests undeclared sandbox capabilities: {', '.join(undeclared)}",
                "level": "warning",
            }
        )

    return {
        "plugin": {
            "name": meta.name if meta else "",
            "version": meta.version if meta else None,
            "description": meta.description if meta else None,
            "author": meta.author if meta else None,
            "homepage": meta.homepage if meta else None,
            "repository": meta.repository if meta else None,
            "license": meta.license if meta else None,
            "keywords": list(meta.keywords) if meta else [],
            "declared_capabilities": [c.value for c in (getattr(meta, "declared_capabilities", ()))],
            "capabilities": aggregated_caps,
            "effective_tier": effective_tier,
            "risk_level": risk_level,
            "capability_diff": capability_diff,
        },
        "skills": [_preview_skill(idx, skill, context) for idx, skill in enumerate(result.skills)],
        "servers": [_preview_server(idx, server, context) for idx, server in enumerate(result.servers)],
        "agents": [_preview_agent(idx, agent, result, context) for idx, agent in enumerate(result.agents)],
        "deployment": {"allows_local_skills": context.allows_local_skills, "allow_stdio": context.allow_stdio},
        "workspace_file_count": len(result.workspace_files),
        "diagnostics": diagnostics_list,
        "is_valid": meta is not None,
    }
