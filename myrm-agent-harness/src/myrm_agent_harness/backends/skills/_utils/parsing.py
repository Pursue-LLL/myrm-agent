"""[INPUT]
- myrm_agent_harness.backends.skills._utils.contract::_FRONTMATTER_MEMO / _extract_str_list / _parse_requires / _parse_skill_contract (POS: skills _utils 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.backends.skills._utils.frontmatter::_MAX_COMPATIBILITY_LENGTH / _MAX_NAME_LENGTH / SkillFrontmatter / _parse_frontmatter_yaml / _validate_and_extract_description / _warn_unknown_fields (POS: skills _utils 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.backends.skills.types::SkillPermission (POS: Framework generic skill system. The stable public entry point stays at)

[OUTPUT]
- parse_skill_frontmatter: Parse YAML frontmatter from SKILL.md (agentskills.io spec compliant).
- _parse_frontmatter_fields: Build a SkillFrontmatter from SKILL.md text (uncached).

[POS]
skills _utils 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import copy
import logging
import re

from myrm_agent_harness.backends.skills._utils.contract import (
    _FRONTMATTER_MEMO,
    _extract_str_list,
    _parse_requires,
    _parse_skill_contract,
)
from myrm_agent_harness.backends.skills._utils.frontmatter import (
    _MAX_COMPATIBILITY_LENGTH,
    _MAX_NAME_LENGTH,
    SkillFrontmatter,
    _parse_frontmatter_yaml,
    _validate_and_extract_description,
    _warn_unknown_fields,
)
from myrm_agent_harness.backends.skills.types import (
    SkillPermission,
)

logger = logging.getLogger(__name__)

def parse_skill_frontmatter(content: str, skill_dir_name: str) -> SkillFrontmatter:
    """Parse YAML frontmatter from SKILL.md (agentskills.io spec compliant).

    Extracts all agentskills.io specification fields plus our extensions:
    - name (optional, max 64 chars, lowercase + hyphens)
    - description (required, truncated to 1024 chars)
    - license (optional)
    - compatibility (optional, truncated to 500 chars)
    - metadata (optional, string key-value pairs)
    - allowed-tools (optional, space-delimited)
    - requires-tools / fallback-for-tools / requires-tool-groups (optional, tool conditional activation)
    - requires (optional, bins/env/config)
    - always (optional, bool)
    - version (optional, string)

    Parsing is memoized per exact text and name; every call returns its own ``SkillFrontmatter``, so a caller may
    mutate it freely.

    Args:
        content: Full SKILL.md file content
        skill_dir_name: Directory name (for validation and fallback)

    Returns:
        SkillFrontmatter with all parsed fields

    Raises:
        SkillMetadataError: If frontmatter is invalid or missing required fields
    """
    template = _FRONTMATTER_MEMO.get_or_compute(
        content,
        lambda: _parse_frontmatter_fields(content, skill_dir_name),
        scope=skill_dir_name,
    )
    return copy.deepcopy(template)


def _parse_frontmatter_fields(content: str, skill_dir_name: str) -> SkillFrontmatter:
    """Build a SkillFrontmatter from SKILL.md text (uncached)."""
    parsed = _parse_frontmatter_yaml(content, skill_dir_name)
    _warn_unknown_fields(parsed, skill_dir_name)
    description = _validate_and_extract_description(parsed, skill_dir_name)

    # name: optional, validate format per agentskills.io spec
    name: str | None = None
    if "name" in parsed:
        raw_name = str(parsed["name"]).strip()
        if len(raw_name) > _MAX_NAME_LENGTH:
            logger.warning(f"Skill '{skill_dir_name}' name exceeds {_MAX_NAME_LENGTH} chars, ignoring")
        else:
            name = raw_name
            if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", raw_name) or "--" in raw_name:
                logger.warning(
                    f"Skill '{skill_dir_name}' name '{raw_name}' does not follow "
                    f"agentskills.io naming convention (lowercase + hyphens only)"
                )

    # license: optional, free-form string
    skill_license: str | None = None
    if "license" in parsed:
        skill_license = str(parsed["license"]).strip() or None

    # compatibility: optional, truncate to 500 chars
    compatibility: str | None = None
    if "compatibility" in parsed:
        compat_raw = str(parsed["compatibility"]).strip()
        if compat_raw:
            if len(compat_raw) > _MAX_COMPATIBILITY_LENGTH:
                logger.warning(
                    f"Skill '{skill_dir_name}' compatibility truncated from "
                    f"{len(compat_raw)} to {_MAX_COMPATIBILITY_LENGTH} chars"
                )
                compat_raw = compat_raw[:_MAX_COMPATIBILITY_LENGTH]
            compatibility = compat_raw

    # metadata: optional, string key-value mapping
    skill_metadata: dict[str, str] = {}
    if "metadata" in parsed and isinstance(parsed["metadata"], dict):
        for k, v in parsed["metadata"].items():
            skill_metadata[str(k)] = str(v)

    # Promote top-level author/homepage into metadata (common convention)
    for key in ("author", "homepage"):
        if key in parsed and key not in skill_metadata:
            raw = str(parsed[key]).strip()
            if raw:
                skill_metadata[key] = raw

    # allowed-tools: optional, space-delimited string or YAML list (normalized to space-delimited)
    allowed_tools: str | None = None
    if "allowed-tools" in parsed:
        raw_allowed_tools = parsed["allowed-tools"]
        if isinstance(raw_allowed_tools, list):
            normalized = " ".join(
                str(item).strip() for item in raw_allowed_tools if item is not None and str(item).strip()
            )
            allowed_tools = normalized or None
        else:
            allowed_tools = str(raw_allowed_tools).strip() or None

    # allowed-domains: optional, list of strings
    allowed_domains: list[str] | None = None
    if "allowed-domains" in parsed:
        allowed_domains = _extract_str_list(parsed.get("allowed-domains"))
        if not allowed_domains:
            allowed_domains = None

    # requires: optional, dependency declaration
    requires = _parse_requires(parsed)

    # Tool-based conditional activation (SKILL.md frontmatter)
    requires_tools = _extract_str_list(parsed.get("requires-tools") or parsed.get("requires_tools"))
    fallback_for_tools = _extract_str_list(parsed.get("fallback-for-tools") or parsed.get("fallback_for_tools"))
    requires_tool_groups = _extract_str_list(
        parsed.get("requires-tool-groups") or parsed.get("requires_tool_groups"),
    )
    fallback_for_tool_groups = _extract_str_list(
        parsed.get("fallback-for-tool-groups") or parsed.get("fallback_for_tool_groups"),
    )

    # always: optional, catalog-slot guarantee above the inline threshold (never body injection)
    always = bool(parsed.get("always", False))

    # model-invocable: optional (default True)
    # Also supports Claude Code's "disable-model-invocation" (inverted boolean)
    model_invocable = True
    if "model-invocable" in parsed:
        model_invocable = bool(parsed["model-invocable"])
    elif "disable-model-invocation" in parsed:
        model_invocable = not bool(parsed["disable-model-invocation"])

    # user-invocable: optional (default True)
    user_invocable = bool(parsed.get("user-invocable", True))

    # version: optional, version string
    version: str | None = None
    if "version" in parsed:
        raw_version = str(parsed["version"]).strip()
        if raw_version:
            version = raw_version

    # category: optional, for UI grouping
    category: str | None = None
    if "category" in parsed:
        raw_category = str(parsed["category"]).strip()
        if raw_category:
            category = raw_category

    # primaryEnv: optional, primary env var name for apiKey mapping
    # Supports both camelCase (external skill formats) and snake_case
    primary_env: str | None = None
    raw_primary_env = parsed.get("primaryEnv") or parsed.get("primary_env")
    if raw_primary_env:
        pe = str(raw_primary_env).strip()
        if pe:
            primary_env = pe

    oauth_issuer: str | None = None
    raw_oauth_issuer = parsed.get("oauth-issuer") or parsed.get("oauth_issuer")
    if raw_oauth_issuer:
        oi = str(raw_oauth_issuer).strip()
        if oi:
            oauth_issuer = oi

    required_oauth_issuers: list[str] = []
    raw_issuers = parsed.get("required_oauth_issuers") or parsed.get("required-oauth-issuers")
    if raw_issuers and isinstance(raw_issuers, list):
        required_oauth_issuers = [str(item).strip() for item in raw_issuers if str(item).strip()]
    elif oauth_issuer:
        required_oauth_issuers = [oauth_issuer]

    required_mcp_server_ids: list[str] = []
    raw_mcps = (
        parsed.get("required_mcp_server_ids")
        or parsed.get("required-mcp-server-ids")
        or parsed.get("required_mcp_servers")
        or parsed.get("required-mcp-servers")
    )
    if raw_mcps and isinstance(raw_mcps, list):
        required_mcp_server_ids = [str(item).strip() for item in raw_mcps if str(item).strip()]

    # required-credential-files: optional, list of credential file paths
    required_credential_files: list[str] = []
    raw_cred_files = parsed.get("required-credential-files") or parsed.get("required_credential_files")
    if raw_cred_files and isinstance(raw_cred_files, list):
        required_credential_files = [str(f).strip() for f in raw_cred_files if str(f).strip()]

    # evolution-locked: optional (default False)
    evolution_locked = False
    if "evolution-locked" in parsed:
        evolution_locked = bool(parsed["evolution-locked"])
    elif "evolution_locked" in parsed:
        evolution_locked = bool(parsed["evolution_locked"])

    # config-schema: optional JSON Schema for typed configuration UI
    config_schema: dict[str, object] | None = None
    raw_schema = parsed.get("config-schema") or parsed.get("config_schema")
    if raw_schema and isinstance(raw_schema, dict):
        config_schema = dict(raw_schema)

    # specialized-model: optional model slug (Model-As-A-Skill)
    specialized_model: str | None = None
    raw_spec_model = (
        parsed.get("specialized-model") or parsed.get("specialized_model") or parsed.get("specializedModel")
    )
    if raw_spec_model:
        sm = str(raw_spec_model).strip()
        if sm:
            specialized_model = sm

    # model-tier: optional model complexity tier (e.g. "simple", "standard", "reasoning")
    model_tier: str | None = None
    raw_model_tier = parsed.get("model-tier") or parsed.get("model_tier") or parsed.get("modelTier")
    if raw_model_tier:
        mt = str(raw_model_tier).strip().lower()
        if mt:
            model_tier = mt

    # scope_agent_id: optional, agent ID that owns this skill
    scope_agent_id: str | None = None
    if "scope_agent_id" in parsed:
        raw_scope = str(parsed["scope_agent_id"]).strip()
        if raw_scope:
            scope_agent_id = raw_scope

    # required_permissions: optional, list of SkillPermission names.
    # Invalid names are skipped with a warning so one typo does not disable a skill.
    required_permissions: list[SkillPermission] = []
    raw_permissions = parsed.get("required_permissions")
    for raw in _extract_str_list(raw_permissions):
        try:
            required_permissions.append(SkillPermission(raw))
        except ValueError:
            logger.warning(
                f"Skill '{skill_dir_name}' declares unknown required_permission "
                f"'{raw}' (valid: {', '.join(p.value for p in SkillPermission)})"
            )

    contract = _parse_skill_contract(parsed, skill_dir_name)

    return SkillFrontmatter(
        description=description,
        name=name,
        license=skill_license,
        compatibility=compatibility,
        metadata=skill_metadata,
        allowed_tools=allowed_tools,
        allowed_domains=allowed_domains,
        requires=requires,
        requires_tools=requires_tools,
        fallback_for_tools=fallback_for_tools,
        requires_tool_groups=requires_tool_groups,
        fallback_for_tool_groups=fallback_for_tool_groups,
        always=always,
        model_invocable=model_invocable,
        user_invocable=user_invocable,
        version=version,
        category=category,
        primary_env=primary_env,
        oauth_issuer=oauth_issuer,
        required_oauth_issuers=required_oauth_issuers,
        required_mcp_server_ids=required_mcp_server_ids,
        required_credential_files=required_credential_files,
        evolution_locked=evolution_locked,
        config_schema=config_schema,
        contract=contract,
        scope_agent_id=scope_agent_id,
        specialized_model=specialized_model,
        model_tier=model_tier,
        required_permissions=required_permissions,
    )
