"""Skill creation service.

[INPUT]
- creation_protocols::SkillWriteBackend, SkillSaveResult, SkillDeleteResult, SkillResourceWriteResult
- packaging.validator::parse_skill_md
- store.sanitizer::SKILL_MD_FILE, SKILL_NAME_PATTERN

[OUTPUT]
- SkillCreationService: local filesystem implementation of SkillWriteBackend
- skill_creation_service: singleton instance

[POS]
Business-layer implementation of SkillWriteBackend protocol.
Stores skills and their resource files in /workspace/skills/{name}/.
Handles auto-enable/disable in user config on save/delete.
Security scanning is handled by the framework-layer ScanningSkillWriteBackend wrapper.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from myrm_agent_harness.agent.skills.discovery.sanitizer import SKILL_MD_FILE, SKILL_NAME_PATTERN
from myrm_agent_harness.api.skills import SkillMetadataError, parse_skill_frontmatter
from myrm_agent_harness.backends.skills.creation_protocols import (
    SkillDeleteResult,
    SkillResourceWriteResult,
    SkillSaveResult,
)

from app.config.settings import settings

logger = logging.getLogger(__name__)

LOCAL_SKILLS_DIR = Path(settings.database.state_dir) / "skills"


class SkillCreationService:
    """Local filesystem implementation of SkillWriteBackend protocol.

    Storage layout:
        ~/.myrm/skills/{name}/SKILL.md          — skill definition
        ~/.myrm/skills/{name}/scripts/...        — supporting scripts
        ~/.myrm/skills/{name}/references/...     — reference documents
        ~/.myrm/skills/{name}/templates/...      — templates
        ~/.myrm/skills/{name}/assets/...         — static assets
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize service with optional custom base path.

        Args:
            base_path: Custom base directory for skill storage (default: LOCAL_SKILLS_DIR)
        """
        self.base_path = Path(base_path) if base_path else LOCAL_SKILLS_DIR

    # ------------------------------------------------------------------
    # save_skill
    # ------------------------------------------------------------------

    async def save_skill(
        self,
        name: str,
        content: str,
        description: str = "",
    ) -> SkillSaveResult:
        """Save skill to local filesystem and auto-enable."""
        validation_error = self._validate_name(name)
        if validation_error:
            return SkillSaveResult(success=False, error=validation_error)
        if not content or not content.strip():
            return SkillSaveResult(success=False, error="Skill content cannot be empty")

        try:
            frontmatter = parse_skill_frontmatter(content, name)
        except SkillMetadataError as exc:
            return SkillSaveResult(success=False, error=str(exc))

        if not description:
            description = frontmatter.description or f"Skill: {name}"

        target_dir = self.base_path / name
        is_new = not (target_dir / SKILL_MD_FILE).exists()
        if is_new and not frontmatter.evolution_locked:
            content = self._ensure_evolution_locked(content)

        return await self._save_local(name, content, description)

    # ------------------------------------------------------------------
    # delete_skill
    # ------------------------------------------------------------------

    async def delete_skill(
        self,
        name: str,
    ) -> SkillDeleteResult:
        """Delete skill directory and auto-disable."""
        validation_error = self._validate_name(name)
        if validation_error:
            return SkillDeleteResult(success=False, skill_name=name, error=validation_error)

        target_dir = self.base_path / name
        if not target_dir.is_dir():
            return SkillDeleteResult(
                success=False,
                skill_name=name,
                error=f"Skill '{name}' not found at {target_dir}",
            )

        await self._auto_disable_local(target_dir)

        try:
            shutil.rmtree(target_dir)

            # ⚡ Trigger O(1) snapshot delete for hot reload
            try:
                import asyncio

                from myrm_agent_harness.backends.skills.snapshot import SQLiteSkillSnapshot

                snapshot_path = self.base_path / ".skills_snapshot.sqlite"

                def _do_delete():
                    snapshot = SQLiteSkillSnapshot(snapshot_path)
                    snapshot.delete_from_path(target_dir / SKILL_MD_FILE)

                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _do_delete)
            except Exception as e:
                logger.warning("Failed to trigger snapshot delete for %s: %s", name, e)

        except Exception as e:
            logger.error("Failed to delete skill directory '%s': %s", target_dir, e)
            return SkillDeleteResult(success=False, skill_name=name, error=f"Delete failed: {e}")

        logger.warning("Deleted skill locally: %s -> %s", name, target_dir)
        return SkillDeleteResult(success=True, skill_name=name)

    # ------------------------------------------------------------------
    # write_resource
    # ------------------------------------------------------------------

    async def write_resource(
        self,
        skill_name: str,
        resource_path: str,
        content: str,
    ) -> SkillResourceWriteResult:
        """Write a resource file into the skill directory."""
        name_error = self._validate_name(skill_name)
        if name_error:
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=name_error,
            )

        skill_dir = self.base_path / skill_name
        if not skill_dir.is_dir():
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=f"Skill '{skill_name}' not found. Create it first with 'save' action.",
            )

        target = (skill_dir / resource_path).resolve()
        containment_error = self._check_path_containment(target, skill_dir)
        if containment_error:
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=containment_error,
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

            # ⚡ Trigger O(1) snapshot upsert if SKILL.md was modified
            if target.name == "SKILL.md":
                try:
                    from myrm_agent_harness.backends.skills.snapshot import SQLiteSkillSnapshot

                    snapshot_path = self.base_path / ".skills_snapshot.sqlite"
                    snapshot = SQLiteSkillSnapshot(snapshot_path)
                    snapshot.upsert_from_path(target, workspace_root=self.base_path)
                except Exception as e:
                    logger.warning("Failed to trigger snapshot upsert for %s: %s", skill_name, e)

        except Exception as e:
            logger.error("Failed to write resource '%s/%s': %s", skill_name, resource_path, e)
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=f"Write failed: {e}",
            )

        logger.warning("Wrote resource: %s/%s", skill_name, resource_path)
        return SkillResourceWriteResult(success=True, skill_name=skill_name, resource_path=resource_path)

    # ------------------------------------------------------------------
    # delete_resource
    # ------------------------------------------------------------------

    async def delete_resource(
        self,
        skill_name: str,
        resource_path: str,
    ) -> SkillResourceWriteResult:
        """Delete a resource file from the skill directory."""
        name_error = self._validate_name(skill_name)
        if name_error:
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=name_error,
            )

        skill_dir = self.base_path / skill_name
        if not skill_dir.is_dir():
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=f"Skill '{skill_name}' not found.",
            )

        target = (skill_dir / resource_path).resolve()
        containment_error = self._check_path_containment(target, skill_dir)
        if containment_error:
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=containment_error,
            )

        if not target.is_file():
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=f"File not found: '{resource_path}'",
            )

        try:
            target.unlink()

            # ⚡ Trigger O(1) snapshot delete if SKILL.md was deleted
            if target.name == "SKILL.md":
                try:
                    import asyncio

                    from myrm_agent_harness.backends.skills.snapshot import SQLiteSkillSnapshot

                    snapshot_path = self.base_path / ".skills_snapshot.sqlite"

                    def _do_delete():
                        snapshot = SQLiteSkillSnapshot(snapshot_path)
                        snapshot.delete_from_path(target)

                    loop = asyncio.get_running_loop()
                    loop.run_in_executor(None, _do_delete)
                except Exception as e:
                    logger.warning("Failed to trigger snapshot delete for %s: %s", skill_name, e)

        except Exception as e:
            logger.error("Failed to delete resource '%s/%s': %s", skill_name, resource_path, e)
            return SkillResourceWriteResult(
                success=False,
                skill_name=skill_name,
                resource_path=resource_path,
                error=f"Delete failed: {e}",
            )

        logger.warning("Deleted resource: %s/%s", skill_name, resource_path)
        return SkillResourceWriteResult(success=True, skill_name=skill_name, resource_path=resource_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_evolution_locked(content: str) -> str:
        """Inject evolution-locked: true into frontmatter for new user-created skills.

        Protects user-created skills from automated curator transitions
        (stale/archive/consolidation) by default. Users can unlock via the UI.
        """
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            return content
        fm_body = fm_match.group(1)
        if re.search(r"^evolution[-_]locked\s*:", fm_body, re.IGNORECASE | re.MULTILINE):
            return content
        new_fm = fm_body.rstrip() + "\nevolution-locked: true\n"
        return content[: fm_match.start(1)] + new_fm + content[fm_match.end(1) :]

    def _validate_name(self, name: str) -> str | None:
        """Validate skill name."""
        if not name or len(name) > 64 or not SKILL_NAME_PATTERN.match(name):
            return f"Invalid skill name: '{name}'"
        return None

    @staticmethod
    def _check_path_containment(resolved_target: Path, skill_dir: Path) -> str | None:
        """Defense-in-depth: verify resolved path stays within skill directory."""
        resolved_dir = skill_dir.resolve()
        if not str(resolved_target).startswith(str(resolved_dir) + "/") and resolved_target != resolved_dir:
            return "Path escapes skill directory (blocked by containment check)."
        return None

    async def _save_local(
        self,
        name: str,
        content: str,
        description: str,
    ) -> SkillSaveResult:
        """Save to local filesystem."""
        target_dir = self.base_path / name
        skill_file = target_dir / SKILL_MD_FILE
        was_updated = skill_file.exists()

        target_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(content, encoding="utf-8")

        # ⚡ Trigger O(1) snapshot upsert for hot reload
        try:
            import asyncio

            from myrm_agent_harness.backends.skills.snapshot import SQLiteSkillSnapshot

            snapshot_path = self.base_path / ".skills_snapshot.sqlite"

            def _do_upsert():
                snapshot = SQLiteSkillSnapshot(snapshot_path)
                snapshot.upsert_from_path(skill_file, workspace_root=self.base_path)

            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _do_upsert)
        except Exception as e:
            logger.warning("Failed to trigger snapshot upsert for %s: %s", name, e)

        await self._auto_enable_local(target_dir)
        self._notify_sync_manifest(name)

        from app.core.skills.providers.local import compute_local_skill_id

        skill_id = compute_local_skill_id(target_dir)

        action = "Updated" if was_updated else "Created"
        logger.warning("%s skill locally: %s -> %s", action, name, target_dir)
        return SkillSaveResult(
            success=True,
            skill_name=name,
            skill_id=skill_id,
            saved_path=str(target_dir),
            was_updated=was_updated,
        )

    def _notify_sync_manifest(self, skill_name: str) -> None:
        """Notify the sync manifest that a local skill was created/updated."""
        try:
            from myrm_agent_harness.agent.skills.sync.idle_integration import _sync_manager_ref

            if _sync_manager_ref is not None:
                _sync_manager_ref.register_local_skill(skill_name)
        except Exception as e:
            logger.debug("Sync manifest notification skipped: %s", e)

    async def _auto_enable_local(self, skill_dir: Path) -> None:
        """Auto-enable skill in user config after save."""
        from app.core.skills.providers.local import compute_local_skill_id
        from app.core.skills.store.service import skills_service

        skill_id = compute_local_skill_id(skill_dir)
        try:
            config = await skills_service.user_config.get_config()
            if skill_id not in config.enabled_local_skill_ids:
                config.enabled_local_skill_ids.append(skill_id)
                await skills_service.user_config.save_config(config)
                logger.warning("Auto-enabled local skill: %s", skill_id)
        except Exception as e:
            logger.warning("Failed to auto-enable local skill %s: %s", skill_id, e)

    async def _auto_disable_local(self, skill_dir: Path) -> None:
        """Auto-disable skill in user config before delete."""
        from app.core.skills.providers.local import compute_local_skill_id
        from app.core.skills.store.service import skills_service

        skill_id = compute_local_skill_id(skill_dir)
        try:
            config = await skills_service.user_config.get_config()
            if skill_id in config.enabled_local_skill_ids:
                config.enabled_local_skill_ids.remove(skill_id)
                await skills_service.user_config.save_config(config)
                logger.warning("Auto-disabled local skill: %s", skill_id)
        except Exception as e:
            logger.warning("Failed to auto-disable local skill %s: %s", skill_id, e)


skill_creation_service = SkillCreationService()
