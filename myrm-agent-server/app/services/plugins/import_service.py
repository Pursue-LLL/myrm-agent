"""Agent Plugins 1.0.0 import orchestration (business layer).

Consumes the framework-level parser (`myrm_agent_harness.agent.plugins`) and
persists components:
  - skills → SkillStore (INSTALLED trust layer, blue-green atomic write)
  - MCP servers → global ``mcpServers`` UserConfig (disabled by default)
  - Agent binding → `mcp_ids` + `skill_ids` on the target Agent profile

The import is fully offline (no LLM calls) and applies per-component failure
isolation so a single invalid skill or MCP server never aborts the whole import.

[INPUT]
- myrm_agent_harness.agent.plugins.parser::AgentPluginParser (POS: framework
  plugin archive parser.)
- myrm_agent_harness.agent.skills.evolution.core.types (POS: skill lineage types.)
- myrm_agent_harness.agent.skills.evolution.db.store::SkillStore (POS: SQLite
  skill persistence; MAX_SKILL_CONTENT_CHARS is the oversized-content SSOT.)
- app.services.skills.store / UserConfig persistence (POS: business skill/MCP stores.)

[OUTPUT]
- confirm_plugin_import: Persist skills, MCP servers, and agent bindings from a
  parsed plugin archive (offline, per-component failure isolation).

[POS]
Business-layer import orchestration for the open-source product: maps framework
parsing results into product persistence (SkillStore, global mcpServers,
Agent profile binding) with blue-green writes and disabled-by-default MCP.
"""

from __future__ import annotations

import asyncio
import logging
import pickle
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.agent.plugins.models import (
    PluginMcpServer,
    PluginParseResult,
    PluginSkill,
)
from myrm_agent_harness.agent.plugins.parser import AgentPluginParser
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

MAX_SKILL_CONTENT_CHARS = SkillStore.MAX_SKILL_CONTENT_CHARS

logger = logging.getLogger(__name__)


class PluginArchiveSecurityError(ValueError):
    """A plugin ZIP was blocked by the archive security policy.

    Carries the canonical ``error_code`` so the API layer can build a
    structured detail payload and the frontend can localize the message.
    """

    def __init__(self, message: str, error_code: str = "") -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class PluginImportSession:
    """A persisted import session created by /preview and consumed by /confirm."""

    plugin_result: PluginParseResult
    skills_by_key: dict[str, PluginSkill] = field(default_factory=dict)
    servers_by_key: dict[str, PluginMcpServer] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginConfirmItem:
    """A confirm decision for a single plugin component."""

    component: str  # "plugin" | "skill:<name>" | "mcp:<name>"
    virtual_id: str  # stage key: skill:<idx> | mcp:<idx>
    resolution: str  # "install" | "skip"
    name: str


class PluginStaging:
    """Persistent staging for parsed plugin sessions (mirrors SkillStagingManager)."""

    def __init__(self, base_dir: Path) -> None:
        self.staging_dir = base_dir / "plugin_staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_id: str, session: PluginImportSession) -> None:
        path = self._session_path(session_id)
        try:
            with open(path, "wb") as f:
                pickle.dump(session, f)
        except Exception as exc:
            logger.error(
                "Failed to save plugin staging session %s: %s", session_id, exc
            )
            raise RuntimeError("Failed to persist the plugin import session.") from exc

    def load_session(self, session_id: str) -> PluginImportSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(
                f"Plugin import session {session_id} not found in staging area."
            )
        try:
            with open(path, "rb") as f:
                loaded = pickle.load(f)  # noqa: S301
            if not isinstance(loaded, PluginImportSession):
                raise RuntimeError("Plugin staging session is corrupted")
            return loaded
        except Exception as exc:
            logger.error(
                "Failed to load plugin staging session %s: %s", session_id, exc
            )
            raise RuntimeError("Failed to read the plugin import session.") from exc

    def cleanup_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning(
                    "Failed to cleanup plugin staging file %s: %s", path, exc
                )

    def _cleanup_expired_sessions_sync(self) -> None:
        """Remove plugin sessions older than the TTL (abandoned uploads)."""
        import time

        now = time.time()
        try:
            for f in self.staging_dir.glob("*.pkl"):
                if f.is_file() and now - f.stat().st_mtime > 86400:
                    try:
                        f.unlink()
                    except OSError:
                        pass
        except Exception as exc:
            logger.warning("Failed to cleanup expired plugin sessions: %s", exc)

    async def cleanup_expired_sessions(self) -> None:
        """Remove plugin sessions older than the TTL via background thread."""
        await asyncio.to_thread(self._cleanup_expired_sessions_sync)

    def _session_path(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.staging_dir / f"{safe_id}.pkl"


def parse_plugin_zip(zip_bytes: bytes) -> PluginParseResult:
    """Parse a plugin ZIP and raise a user-facing error for fatal archive issues."""
    from myrm_agent_harness.backends.skills.scanning.archive_security import (
        ArchiveSecurityError,
        classify_archive_security_issue,
        format_archive_security_user_message,
    )

    try:
        return AgentPluginParser().parse_zip(zip_bytes)
    except ArchiveSecurityError as exc:
        violation = classify_archive_security_issue(exc)
        message = (
            format_archive_security_user_message(violation)
            if violation is not None
            else str(exc)
        )
        error_code = violation.code.value if violation is not None else ""
        raise PluginArchiveSecurityError(message, error_code=error_code) from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded file is not a valid ZIP archive.") from exc


def _scan_skill_security(skill: PluginSkill) -> list[str]:
    """Scan a plugin skill for dangerous content (mirrors batch import).

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


def build_preview_result(result: PluginParseResult) -> dict[str, object]:
    """Serialize a parse result into the preview response payload."""
    meta = result.meta
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
            _preview_skill(idx, skill)
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
        "diagnostics": [
            {
                "component": d.component,
                "code": d.code,
                "message": d.message,
                "level": d.level.value,
            }
            for d in result.diagnostics
        ],
        "is_valid": meta is not None,
    }


def _preview_skill(idx: int, skill: PluginSkill) -> dict[str, object]:
    """Serialize one skill for the preview payload."""
    oversized = _skill_content_too_large(skill)
    return {
        "name": skill.name,
        "description": skill.description,
        "file_count": len(skill.files),
        "virtual_id": f"skill:{idx}",
        # Oversized skills can never be installed; skip the security scan so the
        # preview mirrors confirm-time behavior instead of doing wasted work.
        "security_issues": [] if oversized else _scan_skill_security(skill),
        "oversized_content": oversized,
    }


def _skill_content_too_large(skill: PluginSkill) -> bool:
    """True when the skill content exceeds the framework's storage limit."""
    return bool(skill.content) and len(skill.content) > MAX_SKILL_CONTENT_CHARS


def _server_has_placeholders(server: PluginMcpServer) -> bool:
    from myrm_agent_harness.agent.plugins.mcp_config import has_placeholders

    values: list[str | None] = [server.cwd]
    if server.args:
        values.extend(server.args)
    values.extend(server.raw_env.values())
    return has_placeholders(*values)


async def confirm_plugin_import(
    session: PluginImportSession,
    *,
    skill_decisions: list[PluginConfirmItem],
    server_decisions: list[PluginConfirmItem],
    bind_agent_id: str | None,
) -> dict[str, object]:
    """Persist selected skills + MCP servers and optionally bind them to an agent.

    Skills are installed with ``EvolutionType.FIX`` lineage (imported via plugin).
    MCP servers are appended to the global ``mcpServers`` UserConfig disabled. When
    ``bind_agent_id`` is set, imported skill ids and server names are appended to the
    agent's ``skill_ids`` / ``mcp_ids``.
    """
    skill_records, skill_ids, skipped_skills = _collect_skill_records(
        session, skill_decisions
    )
    server_configs, skipped_servers = _collect_server_configs(session, server_decisions)

    if skill_records:
        await _write_skills(skill_records)
    imported_server_names: list[str] = []
    if server_configs:
        imported_server_names = await _write_mcp_servers(server_configs)
    if bind_agent_id and (skill_ids or imported_server_names):
        await _bind_agent(
            skill_ids=skill_ids,
            server_names=imported_server_names,
            agent_id=bind_agent_id,
        )

    return {
        "imported_skills": len(skill_records),
        "skipped_skills": skipped_skills,
        "imported_servers": len(imported_server_names),
        "skipped_servers": skipped_servers,
    }


def _collect_skill_records(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
) -> tuple[list[SkillRecord], list[str], int]:
    plugin_name = (
        session.plugin_result.meta.name if session.plugin_result.meta else "plugin"
    )
    records: list[SkillRecord] = []
    skill_ids: list[str] = []
    skipped = 0
    for decision in decisions:
        if decision.resolution == "skip":
            skipped += 1
            continue
        skill = session.skills_by_key.get(decision.virtual_id)
        if skill is None:
            skipped += 1
            continue
        if skill.content and len(skill.content) > MAX_SKILL_CONTENT_CHARS:
            logger.warning(
                "Skipping oversized skill '%s' (%d chars, max %d)",
                skill.name,
                len(skill.content),
                MAX_SKILL_CONTENT_CHARS,
            )
            skipped += 1
            continue
        if _scan_skill_security(skill):
            skipped += 1
            continue
        skill_id = str(uuid.uuid4())
        records.append(
            SkillRecord(
                skill_id=skill_id,
                name=skill.name,
                description=skill.description,
                content=skill.content,
                path=f"plugins/{plugin_name}/{skill.name}/SKILL.md",
                lineage=SkillLineage(
                    evolution_type=EvolutionType.FIX,
                    version=1,
                    parent_id=None,
                    change_summary=f"Imported via Agent Plugin '{plugin_name}'",
                    created_by="plugin_import",
                ),
            )
        )
        skill_ids.append(skill_id)
    return records, skill_ids, skipped


async def _write_skills(records: list[SkillRecord]) -> None:
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    store = get_evolution_skill_store()
    await store.save_skills_batch(records)


def _collect_server_configs(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
) -> tuple[list[dict[str, object]], int]:
    configs: list[dict[str, object]] = []
    skipped = 0
    for decision in decisions:
        if decision.resolution == "skip":
            skipped += 1
            continue
        server = session.servers_by_key.get(decision.virtual_id)
        if server is None:
            skipped += 1
            continue
        configs.append(_server_to_config_dict(server))
    return configs, skipped


def _server_to_config_dict(server: PluginMcpServer) -> dict[str, object]:
    """Serialize a plugin MCP server into the mcpServers entry shape."""
    cfg: dict[str, object] = {
        "name": server.name,
        "type": server.server_type,
        "description": "Imported via Agent Plugin",
        "enabled": False,
        "connectTimeout": 15.0,
        "executeTimeout": 120.0,
        "hostSerial": False,
    }
    if server.command:
        cfg["command"] = server.command
    if server.args:
        cfg["args"] = server.args
    if server.url:
        cfg["url"] = server.url
    if server.headers:
        # Persist only header key names (mapped to secret refs) so credential
        # material from package headers is never stored as plaintext.
        cfg["headers"] = {k: ("{{secret:" + k + "}}") for k in server.headers}
    extra_params: dict[str, object] = {}
    if server.cwd:
        extra_params["cwd"] = server.cwd
    if server.raw_env:
        extra_params["env"] = server.raw_env
    if extra_params:
        cfg["extra_params"] = extra_params
    return cfg


async def _write_mcp_servers(
    configs: list[dict[str, object]],
) -> list[str]:
    """Persist MCP servers, skipping existing names; returns persisted names.

    The returned names reflect only entries actually written so callers can
    count/bind exactly what landed (a duplicate name is skipped, not bound).
    """
    from app.services.config.service import config_service

    record = await config_service.get("mcpServers")
    existing: list[dict[str, object]] = []
    if record is not None and isinstance(record.value, list):
        existing = list(record.value)

    existing_names = {
        str(cfg.get("name", "")) for cfg in existing if isinstance(cfg, dict)
    }
    new_configs: list[dict[str, object]] = []
    persisted_names: list[str] = []
    for cfg in configs:
        name = str(cfg.get("name", "")).strip()
        if not name or name in existing_names:
            continue
        entry = {**cfg, "enabled": False}
        existing.append(entry)
        existing_names.add(name)
        new_configs.append(entry)
        persisted_names.append(name)

    if new_configs:
        await config_service.set("mcpServers", existing, device_id="plugin-import")
    return persisted_names


async def _bind_agent(
    agent_id: str,
    *,
    skill_ids: list[str],
    server_names: list[str],
) -> None:
    """Append imported skills + MCP server names to the agent profile.

    Uses a single ``AgentUpdate`` so skill and MCP bindings land atomically.
    Missing agents and duplicate ids are silently tolerated.
    """
    from app.database.dto import AgentUpdate
    from app.services.agent.agent_service import AgentService

    profile = await AgentService.get_agent_by_id(agent_id)
    if profile is None:
        return
    metadata = profile.metadata or {}
    update_fields: dict[str, list[str]] = {}
    if skill_ids:
        existing_skills = metadata.get("skill_ids", [])
        update_fields["skill_ids"] = list(
            dict.fromkeys(
                [*(str(s) for s in existing_skills if isinstance(s, str)), *skill_ids]
            )
        )
    if server_names:
        existing_servers = metadata.get("mcp_ids", [])
        update_fields["mcp_ids"] = list(
            dict.fromkeys(
                [
                    *(str(s) for s in existing_servers if isinstance(s, str)),
                    *server_names,
                ]
            )
        )
    if update_fields:
        await AgentService.update_agent(agent_id, AgentUpdate(**update_fields))
