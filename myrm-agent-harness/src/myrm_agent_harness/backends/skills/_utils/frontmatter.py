"""SKILL.md frontmatter 常量、模型、YAML 解析与字段校验。

[POS]
skills _utils 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import yaml

from myrm_agent_harness.backends.skills.types import (
    SkillContract,
    SkillPermission,
    SkillRequires,
)

_MAX_DESCRIPTION_LENGTH = 1024
_MAX_COMPATIBILITY_LENGTH = 500
_MAX_NAME_LENGTH = 64
_MAX_SKILL_FILE_SIZE = 1 * 1024 * 1024  # 1 MB max for SKILL.md


logger = logging.getLogger(__name__)

class SkillMetadataError(Exception):
    """Skill metadata parsing or validation error."""

    pass


@dataclass
class SkillFrontmatter:
    """Parsed SKILL.md frontmatter data (agentskills.io spec compliant).

    Contains all fields from the agentskills.io specification plus
    our extensions (tool-based conditional activation, dependency requirements,
    hooks, allowed-tools with hook-level control).
    """

    description: str
    """Skill description (truncated to 1024 chars per spec)"""

    name: str | None = None
    """Skill name from frontmatter (may differ from directory name)"""

    license: str | None = None
    """License name or reference"""

    compatibility: str | None = None
    """Environment requirements (truncated to 500 chars per spec)"""

    metadata: dict[str, str] = field(default_factory=dict)
    """Arbitrary key-value metadata (e.g. author, version)"""

    allowed_tools: str | None = None
    """Space-delimited pre-approved tools (experimental per spec)"""

    requires: SkillRequires | None = None
    """External dependency requirements (bins/env/config)"""

    requires_tools: list[str] = field(default_factory=list)
    """Skill hidden when any listed tool is absent from the agent's tool set."""

    fallback_for_tools: list[str] = field(default_factory=list)
    """Skill hidden when any listed tool IS present (fallback for that tool)."""

    requires_tool_groups: list[str] = field(default_factory=list)
    """Skill hidden when any listed tool group is not enabled on the agent."""

    fallback_for_tool_groups: list[str] = field(default_factory=list)
    """Skill hidden when any listed tool group IS enabled (fallback for that group)."""

    always: bool = False
    """Guaranteed a slot in the ``<bound_skills>`` catalog when the bound set exceeds the
    inline threshold. Does NOT inject the SKILL.md body and does NOT enter SystemMessage;
    has no effect at all while the bound set fits inline. See agent/skills/SKILL_SYSTEM.md §4.3."""

    model_invocable: bool = True
    """Whether the model can auto-select this skill via skill_select_tool"""

    user_invocable: bool = True
    """Whether the user can manually trigger this skill (e.g. via / command or UI)"""

    version: str | None = None
    """Skill version string for version management"""

    category: str | None = None
    """Skill category for UI grouping"""

    primary_env: str | None = None
    """Primary environment variable name for apiKey auto-mapping (e.g. "BRAVE_API_KEY").
    When set, users can configure a single apiKey that auto-maps to this env var."""

    oauth_issuer: str | None = None
    """OAuth issuer key for runtime credential injection (e.g. google_workspace).

    Declarative skill contract — business OAuth flows live in the product layer;
    harness uses this only to scope user_credentials_ctx injection during bash.
    """

    required_oauth_issuers: list[str] = field(default_factory=list)
    """Multiple OAuth issuer keys required by this skill."""

    required_mcp_server_ids: list[str] = field(default_factory=list)
    """Multiple MCP server IDs required by this skill for preflight checks."""

    allowed_domains: list[str] | None = None
    """Allowed domains for outbound network requests (DLP protection)."""

    required_credential_files: list[str] = field(default_factory=list)
    """Required credential files for this skill (relative to workspace root)."""

    evolution_locked: bool = False
    """If True, this skill is locked from automatic evolution."""

    config_schema: dict[str, object] | None = None
    """JSON Schema for skill configuration. When provided, enables type-safe
    configuration UI and validation for SkillInstanceConfig.config_overrides.
    Uses a subset of JSON Schema (properties, type, enum, default, required,
    minimum, maximum, format). Example in SKILL.md frontmatter:
        config-schema:
          type: object
          properties:
            api_key: {type: string, format: password, title: API Key}
            timeout: {type: integer, default: 30, minimum: 1, maximum: 300}
    """

    contract: SkillContract | None = None
    """Structured contract parsed from frontmatter and summarised in the skill catalog."""

    scope_agent_id: str | None = None
    """Agent ID that owns this skill (for Multi-Agent scoping)."""

    specialized_model: str | None = None
    """Specialized small or fine-tuned model slug declared for this skill execution (Model-As-A-Skill)."""

    model_tier: str | None = None
    """Recommended model complexity tier for this skill (e.g. 'simple', 'standard', 'reasoning')."""

    required_permissions: list[SkillPermission] = field(default_factory=list)
    """Permissions required by this skill, declared in SKILL.md frontmatter as:

      required_permissions:
        - file_write
        - shell_exec

    Invalid permission names are skipped with a warning (fail-lenient).
    """


def _parse_frontmatter_yaml(content: str, skill_dir_name: str) -> dict[str, object]:
    """Extract and parse YAML frontmatter from SKILL.md content.

    Args:
        content: Full SKILL.md file content
        skill_dir_name: Directory name (for error messages)

    Returns:
        Parsed YAML dict

    Raises:
        SkillMetadataError: If frontmatter is missing or invalid
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        raise SkillMetadataError(
            f"No YAML frontmatter found in SKILL.md.\n"
            f"Expected format (first 3 lines must be):\n"
            f"---\n"
            f"description: Brief description of {skill_dir_name}\n"
            f"---"
        )

    frontmatter_text = match.group(1)

    try:
        parsed = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as e:
        raise SkillMetadataError(f"Invalid YAML syntax in frontmatter: {e}") from e

    if not isinstance(parsed, dict):
        raise SkillMetadataError(f"Frontmatter must be a YAML object, got: {type(parsed).__name__}")

    return parsed


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    """Extract YAML frontmatter and body from markdown content.

    Args:
        content: Full SKILL.md file content

    Returns:
        tuple of (parsed_yaml_dict, body_markdown)
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    body = match.group(2)

    try:
        parsed = yaml.safe_load(frontmatter_text)
        if isinstance(parsed, dict):
            return parsed, body
    except yaml.YAMLError:
        pass

    return {}, body


_KNOWN_FRONTMATTER_FIELDS = frozenset(
    {
        "name",
        "description",
        "version",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
        "allowed-domains",
        "requires",
        "always",
        "model-invocable",
        "user-invocable",
        "disable-model-invocation",
        "hooks",
        "category",
        "author",
        "homepage",
        "tags",
        "primaryEnv",
        "primary_env",
        "oauth-issuer",
        "oauth_issuer",
        "required-oauth-issuers",
        "required_oauth_issuers",
        "required-mcp-server-ids",
        "required_mcp_server_ids",
        "required-mcp-servers",
        "required_mcp_servers",
        "required-credential-files",
        "required_credential_files",
        "evolution-locked",
        "evolution_locked",
        "config-schema",
        "config_schema",
        "contract",
        "requires-tools",
        "requires_tools",
        "fallback-for-tools",
        "fallback_for_tools",
        "requires-tool-groups",
        "requires_tool_groups",
        "fallback-for-tool-groups",
        "fallback_for_tool_groups",
        "scope_agent_id",
        "specialized-model",
        "specialized_model",
        "specializedModel",
        "model-tier",
        "model_tier",
        "modelTier",
        "required_permissions",
    }
)


def _validate_and_extract_description(parsed: dict[str, object], skill_dir_name: str) -> str:
    """Validate and extract description field per agentskills.io spec.

    Truncates to 1024 characters if exceeded. Strips XML angle brackets
    to prevent injection into XML summaries.

    Args:
        parsed: Parsed YAML frontmatter dict
        skill_dir_name: Directory name (for error messages)

    Returns:
        Validated description string (max 1024 chars, XML-safe)
    """
    if "description" not in parsed:
        raise SkillMetadataError(
            f"Required field 'description' missing in frontmatter.\n"
            f"Add this line to your frontmatter:\n"
            f"description: Brief description of {skill_dir_name}"
        )

    description = str(parsed["description"]).strip()
    if not description:
        raise SkillMetadataError(
            f"Field 'description' cannot be empty.\nProvide a meaningful description for {skill_dir_name}"
        )

    if len(description) > _MAX_DESCRIPTION_LENGTH:
        logger.warning(
            f"Skill '{skill_dir_name}' description truncated from {len(description)} to {_MAX_DESCRIPTION_LENGTH} chars"
        )
        description = description[:_MAX_DESCRIPTION_LENGTH]

    if "<" in description or ">" in description:
        logger.warning(f"Skill '{skill_dir_name}' description contains angle brackets, stripping for safety")
        description = description.replace("<", "").replace(">", "")

    return description


def _warn_unknown_fields(parsed: dict[str, object], skill_dir_name: str) -> None:
    """Log warnings for unrecognized frontmatter fields."""
    unknown = set(parsed.keys()) - _KNOWN_FRONTMATTER_FIELDS
    if unknown:
        logger.warning(f"Skill '{skill_dir_name}' has unknown frontmatter fields: {', '.join(sorted(unknown))}")
