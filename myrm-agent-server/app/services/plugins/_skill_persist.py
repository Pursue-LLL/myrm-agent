"""Skill persistence for Agent Plugin imports (business layer).

A plugin skill is installed like every other external skill: through the
quarantine pipeline (lifecycle-script guard → security score over every file,
scripts included → version guard → atomic promote) and then enabled in the user
catalog. The resulting skill is visible, assemblable and readable with its
``scripts/`` and ``references/``, and carries the canonical local skill id that
experts bind to.

[INPUT]
- ._gates::scan_skill_security, skill_block_reason (POS: shared pre-install gates.)
- ._models::PluginImportSession, PluginConfirmItem, ComponentFailure (POS: import DTOs.)
- app.core.skills.marketplace.market_service::market_service (POS: ``install_files`` quarantine pipeline.)
- app.core.skills.discovery.mount::maybe_mount_after_install, resolve_mount_skill_id
  (POS: enable an installed skill in the user catalog; canonical id.)

[OUTPUT]
- SkillImportOutcome: canonical ids of installed skills, skip count, per-skill failures.
- install_plugin_skills: install the selected skills of a parsed package.

[POS]
Business-layer skill installation for plugin imports. Per-skill failure isolation:
a rejected skill is reported and leaves nothing behind; the rest of the import continues.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from myrm_agent_harness.agent.plugins.models import PluginSkill

from . import _gates
from ._models import ComponentFailure, PluginConfirmItem, PluginImportSession

logger = logging.getLogger(__name__)

SKILL_SOURCE = "agent-plugin"
_MAX_REPORTED_ISSUES = 3

__all__ = ["SKILL_SOURCE", "SkillImportOutcome", "install_plugin_skills"]


@dataclass(frozen=True)
class SkillImportOutcome:
    installed_ids: dict[str, str] = field(default_factory=dict)  # package skill name -> canonical skill id
    skipped: int = 0
    failures: tuple[ComponentFailure, ...] = ()


async def install_plugin_skills(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
    *,
    plugin_name: str,
    allows_local_skills: bool,
) -> SkillImportOutcome:
    """Install the accepted skills of ``session``; ``replace`` may also overwrite a newer installed version."""
    installed: dict[str, str] = {}
    failures: list[ComponentFailure] = []
    skipped = 0

    for decision in decisions:
        skill = session.skills_by_key.get(decision.virtual_id)
        if decision.resolution == "skip" or skill is None:
            skipped += 1
            continue

        failure = await _gate_failure(skill, allows_local_skills)
        if failure is None:
            failure = await _install_one(skill.name, skill.files, plugin_name, decision, installed)
        if failure is not None:
            failures.append(failure)

    return SkillImportOutcome(installed_ids=installed, skipped=skipped, failures=tuple(failures))


async def _gate_failure(skill: PluginSkill, allows_local_skills: bool) -> ComponentFailure | None:
    """Pre-install checks shared with the preview (deployment, size, content scan)."""
    blocked = _gates.skill_block_reason(skill, allows_local_skills=allows_local_skills)
    if blocked is not None:
        message = f"Skill '{skill.name}' cannot be installed here ({blocked})"
        logger.warning("Plugin skill '%s' not installed: %s", skill.name, message)
        return ComponentFailure("skill", skill.name, blocked, message)
    issues = await asyncio.to_thread(_gates.scan_skill_security, skill)
    if issues:
        message = "; ".join(issues[:_MAX_REPORTED_ISSUES])
        logger.warning("Plugin skill '%s' blocked by content scan: %s", skill.name, message)
        return ComponentFailure("skill", skill.name, _gates.BLOCK_SECURITY, message)
    return None


async def _install_one(
    name: str,
    files: dict[str, bytes],
    plugin_name: str,
    decision: PluginConfirmItem,
    installed: dict[str, str],
) -> ComponentFailure | None:
    from app.core.skills.discovery.mount import maybe_mount_after_install, resolve_mount_skill_id
    from app.core.skills.marketplace.market_service import market_service

    result = await market_service.install_files(
        f"{SKILL_SOURCE}:{plugin_name}/{name}",
        name,
        files,
        source=SKILL_SOURCE,
        allow_downgrade=decision.resolution == "replace",
    )
    if not result.success:
        code = result.error_code or "install_failed"
        logger.warning("Plugin skill '%s' rejected by the install pipeline (%s): %s", name, code, result.error)
        return ComponentFailure("skill", name, code, result.error or "Skill installation failed")

    skill_id = resolve_mount_skill_id(result)
    if skill_id is None:
        return ComponentFailure("skill", name, "install_failed", f"Skill '{name}' installed without a resolvable id")
    installed[name] = skill_id

    mount = await maybe_mount_after_install(result, agent_id=None, mount_to_agent=True)
    if mount is not None and not mount.mounted:
        # Files are in place and usable; the user can still enable the skill from the catalog.
        return ComponentFailure("skill", name, "enable_failed", mount.error or "Skill installed but not enabled")
    return None
