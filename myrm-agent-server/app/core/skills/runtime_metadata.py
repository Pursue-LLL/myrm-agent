"""Catalog skill to agent-runtime metadata adapter.

[INPUT]
app.core.skills.models::Skill (POS: catalog skill record)
app.core.skills.utils::normalize_skill_name (POS: runtime skill naming)
myrm_agent_harness.backends.skills.types::SkillMetadata, SkillPermission, SkillTrust (POS: framework runtime types)

[OUTPUT]
skill_to_runtime_metadata: build the SkillMetadata the agent runtime consumes from a catalog Skill

[POS]
Reverse of ``Skill.from_metadata``. Skills bound to an agent reach the runtime through the catalog record,
so every field that drives runtime behaviour (requirement gating, trust and tool limits, always-on and
invocation flags, env/OAuth injection) is carried here in one place. Availability is not copied: the
runtime gates recompute it against the live environment. Fields that live only in SKILL.md (hooks,
conditional-activation tool lists, contract, model routing) are not part of the catalog record.
"""

from __future__ import annotations

from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillPermission, SkillTrust

from app.core.skills.models import Skill
from app.core.skills.utils import normalize_skill_name

_PERMISSIONS_BY_VALUE = {permission.value: permission for permission in SkillPermission}


def _runtime_trust(catalog_trust: str) -> SkillTrust:
    """Only an explicit ``trusted`` record earns full tool authority; anything else is attenuated."""
    return SkillTrust.TRUSTED if catalog_trust == "trusted" else SkillTrust.INSTALLED


def _scanner_clean(skill: Skill, trust: SkillTrust) -> bool:
    """Whether the stored scan found nothing; an unscanned installed skill is not assumed clean."""
    if skill.security is not None:
        return skill.security.total_findings == 0
    return trust is SkillTrust.TRUSTED


def _permissions(values: list[str]) -> list[SkillPermission]:
    return [_PERMISSIONS_BY_VALUE[value] for value in values if value in _PERMISSIONS_BY_VALUE]


def skill_to_runtime_metadata(skill: Skill) -> SkillMetadata:
    """Adapt a catalog ``Skill`` to runtime ``SkillMetadata``.

    Raises:
        ValueError: when the skill name cannot be turned into a runtime name.
    """
    trust = _runtime_trust(skill.trust)
    declares_requires = bool(skill.requires.bins or skill.requires.env or skill.requires.config)
    return SkillMetadata(
        name=normalize_skill_name(skill.name),
        description=skill.description or "",
        token_cost=skill.token_cost,
        storage_skill_id=skill.id,
        storage_path=skill.storage_path,
        version=skill.version,
        requires=skill.requires if declares_requires else None,
        always=skill.always,
        model_invocable=skill.model_invocable,
        user_invocable=skill.user_invocable,
        primary_env=skill.primary_env,
        oauth_issuer=skill.oauth_issuer,
        required_oauth_issuers=list(skill.required_oauth_issuers),
        required_mcp_server_ids=list(skill.required_mcp_server_ids),
        allowed_domains=skill.allowed_domains,
        allowed_tools=skill.allowed_tools,
        required_permissions=_permissions(skill.required_permissions),
        evolution_locked=skill.evolution_locked,
        scope_agent_id=skill.scope_agent_id,
        config_schema=skill.config_schema,
        trust=trust,
        scanner_clean=_scanner_clean(skill, trust),
        scan_summary=skill.security,
    )
