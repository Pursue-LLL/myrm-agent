"""Data types of the expert export (business layer).

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginAgent, PluginMcpServer (POS: portable records.)
- myrm_agent_harness.backends.profiles.types::AgentProfile (POS: stored expert.)

[OUTPUT]
- Omit: reason codes of everything an export leaves out (the UI localizes them).
- OmittedItem: one entry of the "not included in the package" list.
- ExportError: a request the export refuses, with a machine-readable code.
- ExportedSkill / ExpertDraft / ExportPlan: the dependency closure of one expert.

[POS]
Plain data shared by the closure collector and the export facade. No I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from myrm_agent_harness.agent.plugins.models import PluginAgent, PluginMcpServer

__all__ = [
    "ExpertDraft",
    "ExportError",
    "ExportErrorCode",
    "ExportPlan",
    "ExportedSkill",
    "Omit",
    "OmittedItem",
]


class ExportErrorCode(StrEnum):
    EXPERT_NOT_FOUND = "expert_not_found"
    BUILT_IN_EXPERT = "built_in_expert"
    CHANGED_SINCE_PREVIEW = "export_changed_since_preview"
    REVIEW_REQUIRED = "redaction_review_required"
    PACKAGE_REJECTED = "package_rejected"


class ExportError(Exception):
    """The export request is refused; ``code`` tells the caller why."""

    def __init__(self, code: ExportErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Omit(StrEnum):
    """Why something that belongs to an expert is not in its package."""

    BINARY_FILE = "binary_file"  # content cannot be reviewed for secrets
    OVERSIZED_FILE = "oversized_file"
    TOTAL_SIZE_EXCEEDED = "total_size_exceeded"
    EXCLUDED_PATH = "excluded_path"  # hidden or build-noise paths (.env, node_modules, ...)
    SKILL_UNAVAILABLE = "skill_unavailable"  # not installed, not readable or without SKILL.md
    CONNECTOR_MISSING = "connector_missing"
    CONNECTOR_LOCAL_PATH = "local_path"  # launches something from a path on this machine
    CONNECTOR_BUNDLED_FILES = "bundled_files"  # depends on files shipped by another package
    CONNECTOR_SECRET_MATERIAL = "contains_secret"  # credentials sit inside the connector declaration
    CONNECTOR_UNSUPPORTED = "unsupported_connector"
    EXPERT_BUILT_IN = "built_in_expert"
    EXPERT_MISSING = "expert_missing"
    EXPERT_CYCLE = "cycle_edge"  # a sub-expert link that would loop back to a parent
    TOO_MANY_EXPERTS = "too_many_experts"
    SUB_EXPERT_WORKSPACE = "sub_expert_workspace"  # workspace templates ship with the entry expert only
    MAY_CARRY_CREDENTIALS = "may_carry_credentials"  # configured services that could hold credentials
    ABOVE_DEFAULT = "above_default"  # loop budget above the system default is never shared


@dataclass(frozen=True)
class OmittedItem:
    kind: str  # skill | skill_file | connector | expert | workspace_file | setting
    name: str
    reason: Omit
    owner: str | None = None  # the expert or skill the item belongs to


@dataclass(frozen=True)
class ExportedSkill:
    """A skill that ships inside the package, with its reviewable file tree."""

    package_name: str  # directory name inside the package; experts reference the skill by it
    display_name: str
    version: str | None
    origin_source: str | None  # install provenance label; None for skills authored here
    files: Mapping[str, bytes]


@dataclass(frozen=True)
class ExpertDraft:
    """One expert of the package: the portable record plus the stored profile's identity."""

    agent_id: str
    agent: PluginAgent


@dataclass
class ExportPlan:
    """Everything one expert needs, collected before redaction and packaging."""

    plugin_name: str
    experts: list[ExpertDraft] = field(default_factory=list)  # entry expert first
    skills: list[ExportedSkill] = field(default_factory=list)
    preset_skill_names: list[str] = field(default_factory=list)  # referenced by name, not shipped
    connectors: list[PluginMcpServer] = field(default_factory=list)
    workspace_files: dict[str, bytes] = field(default_factory=dict)
    omitted: list[OmittedItem] = field(default_factory=list)

    @property
    def entry(self) -> PluginAgent:
        return self.experts[0].agent
