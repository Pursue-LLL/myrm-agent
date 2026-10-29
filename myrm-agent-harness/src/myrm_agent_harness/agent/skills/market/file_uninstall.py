"""Skill uninstallation: removes a local skill together with the child skills its plugin installed.

[INPUT]
- backends.skills.local_skill_id::resolve_local_install_dir (POS: Maps a local skill id back to its install directory)
- backends.skills.market_protocols::SkillInstallResult (POS: Typed install outcome)
- backends.skills.scanning.path_security::assert_safe_install_target (POS: Refuses symlinked, escaping or bucket-colliding targets)
- .helpers::read_origin (POS: Provenance file)
- .transaction::read_receipt_file (POS: Install receipt listing the skills a plugin installed)

[OUTPUT]
- uninstall_skill: Remove a locally installed skill and cascade-remove the child skills it installed.

[POS]
The one uninstall path of the skill market. The market service passes its install root, so the removal itself reads no
module-level location.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from myrm_agent_harness.backends.skills.local_skill_id import resolve_local_install_dir
from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult
from myrm_agent_harness.backends.skills.scanning.path_security import assert_safe_install_target

from .helpers import read_origin
from .transaction import read_receipt_file

logger = logging.getLogger(__name__)


async def uninstall_skill(install_root: Path, skill_id: str) -> SkillInstallResult:
    """Uninstall a locally installed skill and cascade-remove any child skills using its receipt."""
    if not skill_id.startswith("local::"):
        return SkillInstallResult(
            success=False,
            error=f"Only local skills can be uninstalled via this method: {skill_id}",
        )

    target_dir = resolve_local_install_dir(skill_id, install_root)
    if target_dir is None:
        return SkillInstallResult(success=False, error=f"Skill directory not found for id: {skill_id}")

    # A rejected target must not cost the user its child skills, so the check comes before any removal.
    try:
        assert_safe_install_target(target_dir)
    except Exception as e:
        return SkillInstallResult(success=False, error=f"Failed to remove skill directory: {e}")

    skill_name = target_dir.name
    uninstalled_skills = [skill_name]

    # 1. Inspect receipt if present for precise forensic accounting
    receipt = read_receipt_file(target_dir)

    # 2. Cascade uninstall child skills registered to this parent plugin
    if install_root.exists():
        for child_dir in list(install_root.iterdir()):
            if child_dir.is_dir() and child_dir != target_dir:
                child_origin = read_origin(child_dir)
                is_child = (
                    child_origin.get("parent_plugin") == skill_name
                    or child_origin.get("skill_id") == skill_id
                    or (receipt and child_dir.name in receipt.installed_skills)
                )
                if is_child:
                    try:
                        shutil.rmtree(child_dir)
                        uninstalled_skills.append(child_dir.name)
                        logger.info(
                            "Cascade uninstalled child skill %s of parent %s",
                            child_dir.name,
                            skill_name,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to cascade remove child skill %s: %s",
                            child_dir.name,
                            exc,
                        )

    # 3. Remove main target directory
    try:
        shutil.rmtree(target_dir)
    except Exception as e:
        return SkillInstallResult(success=False, error=f"Failed to remove skill directory: {e}")

    logger.info("Uninstalled skill: %s (total cleaned: %s)", skill_name, uninstalled_skills)
    return SkillInstallResult(
        success=True,
        skill_name=skill_name,
        skill_id=skill_id,
        installed_path=str(target_dir),
        installed_skills=uninstalled_skills,
        receipt=receipt,
    )
