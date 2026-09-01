"""Shared data models for Agent Plugins 1.0.0 import orchestration.

Session and decision DTOs shared by the import pipeline modules
(``import_service`` / ``_staging`` / ``_mcp_persist``).

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginParseResult, PluginSkill,
  PluginMcpServer (POS: framework parser output dataclasses.)

[OUTPUT]
- PluginImportSession: persisted preview session consumed by /confirm.
- PluginConfirmItem: a single confirm decision for a plugin component.

[POS]
Business-layer DTOs for plugin import orchestration (parse-only session +
per-component confirm decisions).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from myrm_agent_harness.agent.plugins.models import (
    PluginAgent,
    PluginMcpServer,
    PluginParseResult,
    PluginSkill,
)


@dataclass(frozen=True)
class PluginImportSession:
    """A persisted import session created by /preview and consumed by /confirm."""

    plugin_result: PluginParseResult
    skills_by_key: dict[str, PluginSkill] = field(default_factory=dict)
    servers_by_key: dict[str, PluginMcpServer] = field(default_factory=dict)
    agents_by_key: dict[str, PluginAgent] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginConfirmItem:
    """A confirm decision for a single plugin component."""

    component: str  # "plugin" | "skill:<name>" | "mcp:<name>" | "agent:<name>"
    virtual_id: str  # stage key: skill:<idx> | mcp:<idx> | agent:<idx>
    resolution: str  # "install" | "replace" | "skip"
    name: str
