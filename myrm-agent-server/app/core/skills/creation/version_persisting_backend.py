"""Wrap SkillWriteBackend to mirror agent meta-tool saves into server version SSOT.

[INPUT]
- creation_protocols::SkillWriteBackend, SkillSaveResult (POS: harness write protocol)

[OUTPUT]
- VersionPersistingSkillWriteBackend: delegates save_skill then persists SKILL.md snapshot

[POS]
Server-only wrapper around SkillCreationService; keeps harness free of SQL / reverse deps.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.backends.skills.creation_protocols import (
    SkillDeleteResult,
    SkillResourceWriteResult,
    SkillSaveResult,
)

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.creation_protocols import SkillWriteBackend

logger = logging.getLogger(__name__)


class VersionPersistingSkillWriteBackend:
    """Persist DB skill_versions after successful agent save_skill (idempotent by content hash)."""

    def __init__(self, inner: SkillWriteBackend) -> None:
        self._inner = inner

    async def _resolve_skill_id(self, skill_name: str) -> str | None:
        from app.services.skills.write_orchestrator import resolve_skill_id_by_name

        return await resolve_skill_id_by_name(skill_name)

    async def save_skill(
        self,
        name: str,
        content: str,
        description: str = "",
    ) -> SkillSaveResult:
        result = await self._inner.save_skill(name, content, description)
        if not result.success:
            return result

        skill_id = result.skill_id
        if not skill_id:
            from app.services.skills.write_orchestrator import resolve_skill_id_by_name

            skill_id = await resolve_skill_id_by_name(name)
        if not skill_id:
            logger.warning("Version persist skipped: could not resolve skill_id for name %s", name)
            return result

        try:
            from app.services.skills.write_orchestrator import persist_skill_md_snapshot

            await persist_skill_md_snapshot(
                skill_id,
                content,
                created_by="agent_meta_tool",
                sync_disk=False,
            )
        except Exception as exc:
            logger.error("Failed to persist skill version after meta-tool save for %s: %s", skill_id, exc)
            from app.services.skills.write_orchestrator import restore_skill_md_from_active_version

            restored = await restore_skill_md_from_active_version(skill_id)
            if not restored:
                logger.warning(
                    "Could not restore SKILL.md from active version after persist failure for %s",
                    skill_id,
                )
            return SkillSaveResult(
                success=False,
                skill_name=name,
                skill_id=skill_id,
                error=f"Skill version snapshot failed; disk reverted when possible: {exc}",
            )
        return result

    async def delete_skill(self, name: str) -> SkillDeleteResult:
        return await self._inner.delete_skill(name)

    async def write_resource(
        self,
        skill_name: str,
        resource_path: str,
        content: str,
    ) -> SkillResourceWriteResult:
        result = await self._inner.write_resource(skill_name, resource_path, content)
        if not result.success:
            return result
        skill_id = await self._resolve_skill_id(skill_name)
        if skill_id:
            try:
                from app.services.skills.write_orchestrator import record_resource_package_revision

                await record_resource_package_revision(
                    skill_id,
                    resource_path,
                    content,
                    created_by="agent_meta_tool",
                )
            except Exception as exc:
                logger.error("Package revision failed after resource write for %s: %s", skill_name, exc)
                return SkillResourceWriteResult(
                    success=False,
                    skill_name=skill_name,
                    resource_path=resource_path,
                    error=f"Resource saved but revision snapshot failed: {exc}",
                )
        return result

    async def delete_resource(self, skill_name: str, resource_path: str) -> SkillResourceWriteResult:
        return await self._inner.delete_resource(skill_name, resource_path)
