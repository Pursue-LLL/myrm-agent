"""Preview serialization and security checks for Agent Plugins 1.0.0 (business layer).

Builds preview payloads for uploaded plugin packages and performs fast offline
pre-validation (content size limits, schema structure, skill AST/regex security).

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginParseResult, PluginSkill, PluginMcpServer (POS: parsed plugin models.)
- myrm_agent_harness.agent.skills.evolution.db.store::SkillStore (POS: storage size limits.)
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: active skill name lookup.)

[OUTPUT]
- build_preview_result: build structured preview dictionary for plugin import wizard.
- load_existing_skill_ids: load active skills map for collision detection.
- scan_skill_security: validate skill content security rules.
- skill_content_too_large: check whether skill content exceeds storage ceiling.

[POS]
Business-layer preview builder and offline validation logic for uploaded agent plugin archives.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

if TYPE_CHECKING:
    from myrm_agent_harness.agent.plugins.models import (
        PluginMcpServer,
        PluginParseResult,
        PluginSkill,
    )

logger = logging.getLogger(__name__)

MAX_SKILL_CONTENT_CHARS = SkillStore.MAX_SKILL_CONTENT_CHARS

__all__ = [
    "build_preview_result",
    "load_existing_skill_ids",
    "scan_skill_security",
    "skill_content_too_large",
]


def scan_skill_security(skill: PluginSkill) -> list[str]:
    """Offline static security scan of a skill's content before preview/confirm.

    Returns a list of human-readable issues; an empty list means the skill passed.
    A scanner failure is treated as unsafe (fail-closed) so a broken validator
    never lets a skill install silently or aborts the whole import.
    """
    from myrm_agent_harness.agent.skills.optimization.config import SecurityConfig
    from myrm_agent_harness.agent.skills.optimization.security import (
        SkillSecurityValidator,
    )

    try:
        validator = SkillSecurityValidator(config=SecurityConfig())
        full_skill = f"---\nname: {skill.name}\ndescription: {skill.description}\n---\n{skill.content}"
        result = validator.validate_skill(full_skill)
    except Exception as exc:  # fail-closed: unable to verify -> blocked
        logger.warning("Skill security scan failed for %r: %s", skill.name, exc)
        return [f"Security scan failed: {exc}"]
    return result.issues if not result.passed else []


def load_existing_skill_ids() -> dict[str, str]:
    """Map active skill names to their skill_ids (conflict-detection SSOT).

    Queried at preview and again at confirm time so the decision always reflects
    the latest store state (preview flags are UI hints only, never trusted).
    """
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    store = get_evolution_skill_store()
    return {skill.name: skill.skill_id for skill in store.get_active_skills()}


def skill_content_too_large(skill: PluginSkill) -> bool:
    """True when the skill content exceeds the framework's storage limit."""
    return bool(skill.content) and len(skill.content) > MAX_SKILL_CONTENT_CHARS


def _server_has_placeholders(server: PluginMcpServer) -> bool:
    from myrm_agent_harness.agent.plugins.mcp_config import has_placeholders

    values: list[str | None] = [server.cwd]
    if server.args:
        values.extend(server.args)
    values.extend(server.raw_env.values())
    return has_placeholders(*values)


def _preview_skill(
    idx: int, skill: PluginSkill, existing_names: set[str]
) -> dict[str, object]:
    """Serialize one skill for the preview payload."""
    oversized = skill_content_too_large(skill)
    scan_fn = scan_skill_security
    import sys

    svc = sys.modules.get("app.services.plugins.import_service")
    if svc is not None and hasattr(svc, "_scan_skill_security"):
        scan_fn = svc._scan_skill_security
    return {
        "name": skill.name,
        "description": skill.description,
        "file_count": len(skill.files),
        "virtual_id": f"skill:{idx}",
        # Oversized skills can never be installed; skip the security scan so the
        # preview mirrors confirm-time behavior instead of doing wasted work.
        "security_issues": [] if oversized else scan_fn(skill),
        "oversized_content": oversized,
        "conflict": skill.name in existing_names,
    }


def build_preview_result(
    result: PluginParseResult,
    existing_names: set[str] | None = None,
) -> dict[str, object]:
    """Serialize a parse result into the preview response payload.

    ``existing_names`` marks skills that already exist in the store so the UI
    can offer replace/skip instead of silently duplicating them.
    """
    meta = result.meta
    existing = existing_names or set()

    from ._agent_persist import MAX_TEMPLATE_FILE_BYTES, MAX_TOTAL_TEMPLATE_BYTES

    diagnostics_list: list[dict[str, object]] = [
        {
            "component": d.component,
            "code": d.code,
            "message": d.message,
            "level": d.level.value,
        }
        for d in result.diagnostics
    ]

    total_ws_bytes = 0
    for rel_path, content in result.workspace_files.items():
        file_len = len(content)
        if file_len > MAX_TEMPLATE_FILE_BYTES:
            diagnostics_list.append(
                {
                    "component": f"workspace:{rel_path}",
                    "code": "OVERSIZED_TEMPLATE_FILE",
                    "message": (
                        f"Workspace template file '{rel_path}' ({file_len} bytes) "
                        f"exceeds 1MB limit ({MAX_TEMPLATE_FILE_BYTES} bytes) and will be skipped"
                    ),
                    "level": "warning",
                }
            )
        elif total_ws_bytes + file_len > MAX_TOTAL_TEMPLATE_BYTES:
            diagnostics_list.append(
                {
                    "component": f"workspace:{rel_path}",
                    "code": "OVERSIZED_WORKSPACE_TOTAL",
                    "message": (
                        f"Workspace template file '{rel_path}' exceeds cumulative 5MB limit "
                        f"({MAX_TOTAL_TEMPLATE_BYTES} bytes) and will be skipped"
                    ),
                    "level": "warning",
                }
            )
        else:
            total_ws_bytes += file_len

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
        },
        "skills": [
            _preview_skill(idx, skill, existing)
            for idx, skill in enumerate(result.skills)
        ],
        "servers": [
            {
                "name": server.name,
                "type": server.server_type,
                "command": server.command,
                "url": server.url,
                "env_key_count": len(server.env_key_names),
                "has_placeholders": _server_has_placeholders(server),
                "virtual_id": f"mcp:{idx}",
            }
            for idx, server in enumerate(result.servers)
        ],
        "agents": [
            {
                "name": agent.name,
                "description": agent.description,
                "system_prompt": agent.system_prompt,
                "max_iterations": agent.max_iterations,
                "skill_names": list(agent.skill_names),
                "tool_names": list(agent.tool_names),
                "mcp_names": list(agent.mcp_names),
                "subagent_names": list(agent.subagent_names),
                "is_subagent": agent.is_subagent,
                "is_entry_agent": agent.is_entry_agent,
                "virtual_id": f"agent:{idx}",
            }
            for idx, agent in enumerate(result.agents)
        ],
        "workspace_file_count": len(result.workspace_files),
        "diagnostics": diagnostics_list,
        "is_valid": meta is not None,
    }
