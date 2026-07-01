"""Business-layer Skill Discovery Service.

Wraps the framework-layer BaseSkillDiscoveryService to add:
- Integration with app.config.settings (e.g., GitHub token)
- SSE ServerEventBus progress emission
- Auto-enabling of skills in user_config
- Integration with installed versions
"""

import importlib
import logging
from pathlib import Path
from typing import cast

from myrm_agent_harness.agent.skills.discovery.service import (
    BaseSkillDiscoveryService,
    EnrichedSearchResult,
)
from myrm_agent_harness.agent.skills.discovery.sources.base import SkillSource
from myrm_agent_harness.agent.skills.discovery.sources.github import GitHubRef, analyze_github_url
from myrm_agent_harness.backends.skills.discovery_protocols import InstalledSkillInfo, SkillInstallResult

logger = logging.getLogger(__name__)


class _AppSkillStore:
    """Adapts business-layer skills_service to framework-layer InstalledSkillStore protocol."""

    async def list_installed(
        self,
        *,
        skill_type: str | None = None,
    ) -> list[InstalledSkillInfo]:
        from myrm_agent_harness.toolkits.storage.types import SkillType

        from app.core.skills.store.service import skills_service

        st = SkillType(skill_type) if skill_type else None
        skills = await skills_service.list_skills(skill_type=st)
        return [
            InstalledSkillInfo(id=s.id, name=s.name, description=s.description, version=s.version, tags=s.tags) for s in skills
        ]

    async def get_installed(self, skill_id: str) -> InstalledSkillInfo | None:
        from app.core.skills.store.service import skills_service

        skill = await skills_service.get_skill(skill_id)
        if not skill:
            return None
        return InstalledSkillInfo(
            id=skill.id, name=skill.name, description=skill.description, version=skill.version, tags=skill.tags
        )


class SkillDiscoveryService:
    def __init__(self) -> None:
        from app.config.settings import settings

        github_token = settings.services.github_token.get_secret_value() or None
        self._base = BaseSkillDiscoveryService(github_token=github_token, skill_store=_AppSkillStore())
        self._github_token = github_token

    @property
    def _sources(self) -> list[SkillSource]:
        """Framework discovery sources (for auto-update and tooling)."""
        return cast(list[SkillSource], self._base._sources)

    async def search(
        self,
        query: str,
        limit: int = 30,
    ) -> list[EnrichedSearchResult]:
        installed_versions = await self._get_installed_versions()
        return cast(
            list[EnrichedSearchResult],
            await self._base.search(query, limit=limit, installed_versions_map=installed_versions),
        )

    async def install(
        self,
        skill_id: str,
        source: str,
    ) -> SkillInstallResult:
        def progress_callback(sid: str, stage: str, message: str) -> None:
            self._emit_progress(sid, stage, message)

        result = await self._base.install(skill_id, source, progress_callback=progress_callback)
        if result.success and result.installed_path and "already installed" not in result.installed_path:
            await self._auto_enable_local_skill(Path(result.installed_path))
        return result

    async def install_from_url(
        self,
        url: str,
    ) -> SkillInstallResult:
        def progress_callback(sid: str, stage: str, message: str) -> None:
            self._emit_progress(sid, stage, message)

        result = await self._base.install_from_url(url, progress_callback=progress_callback)
        if result.success and result.installed_path:
            await self._auto_enable_local_skill(Path(result.installed_path))
        return result

    async def analyze_url(self, url: str) -> list[dict[str, object]]:
        """Analyze a GitHub URL and return a list of specific subdirectories that contain skills."""
        import asyncio
        import re

        import httpx

        try:
            installed_versions = await self._get_installed_versions()
            installed_names = {k for k in installed_versions.keys()}

            refs = await analyze_github_url(url, token=self._github_token)

            async def _fetch_metadata(r: GitHubRef) -> dict[str, object]:
                base = f"https://github.com/{r.owner}/{r.repo}"
                name = r.subdirectory.split("/")[-1] if r.subdirectory else r.repo
                full_url = f"{base}/tree/{r.ref}/{r.subdirectory}" if (r.subdirectory and r.ref) else base
                description = ""

                # Fetch raw SKILL.md to get true name and description
                raw_base = f"https://raw.githubusercontent.com/{r.owner}/{r.repo}/{r.ref or 'HEAD'}"
                raw_path = f"{r.subdirectory}/SKILL.md" if r.subdirectory else "SKILL.md"

                headers = {}
                if self._github_token:
                    headers["Authorization"] = f"token {self._github_token}"

                async with httpx.AsyncClient(timeout=5.0) as client:
                    try:
                        resp = await client.get(f"{raw_base}/{raw_path}", headers=headers)
                        if resp.status_code == 200:
                            content = resp.text
                            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
                            if match:
                                yaml_mod = importlib.import_module("yaml")
                                frontmatter = yaml_mod.safe_load(match.group(1))
                                if isinstance(frontmatter, dict):
                                    name = str(frontmatter.get("name", name))
                                    description = str(frontmatter.get("description", description))
                    except Exception as e:
                        logger.debug("Failed to fetch SKILL.md for %s: %s", raw_path, e)

                is_installed = name.lower() in installed_names
                return {"url": full_url, "name": name, "description": description, "is_installed": is_installed}

            sem = asyncio.Semaphore(10)

            async def _bounded_fetch(r: GitHubRef) -> dict[str, object]:
                async with sem:
                    return await _fetch_metadata(r)

            results = await asyncio.gather(*[_bounded_fetch(r) for r in refs])
            return list(results)
        except Exception as e:
            logger.warning("Failed to analyze GitHub URL %s: %s", url, e)
            return []

    async def uninstall(
        self,
        skill_id: str,
    ) -> SkillInstallResult:
        result = await self._base.uninstall(skill_id)
        if result.success:
            await self._auto_disable_local_skill(skill_id)
            logger.info("Uninstalled skill: %s", skill_id)
        return result

    async def _get_installed_versions(self) -> dict[str, str]:
        from app.core.skills.store.service import skills_service

        try:
            skills = await skills_service.list_skills()
            return {s.name.lower(): s.version for s in skills}
        except Exception as e:
            logger.warning("Failed to fetch installed skills for version comparison: %s", e)
            return {}

    def _emit_progress(self, skill_id: str, stage: str, message: str) -> None:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.SKILL_INSTALL_PROGRESS,
                data={"skill_id": skill_id, "stage": stage, "message": message},
            )
        )

    async def _auto_enable_local_skill(self, skill_dir: Path) -> None:
        from app.core.skills.providers.local import compute_local_skill_id
        from app.core.skills.store.service import skills_service

        skill_id = compute_local_skill_id(skill_dir)
        try:
            config = await skills_service.user_config.get_config()
            if skill_id not in config.enabled_local_skill_ids:
                config.enabled_local_skill_ids.append(skill_id)
                await skills_service.user_config.save_config(config)
                logger.info("Auto-enabled local skill: %s", skill_id)
        except Exception as e:
            logger.warning("Failed to auto-enable local skill %s: %s", skill_id, e)

    async def _auto_disable_local_skill(self, skill_id: str) -> None:
        from app.core.skills.store.service import skills_service

        try:
            config = await skills_service.user_config.get_config()
            if skill_id in config.enabled_local_skill_ids:
                config.enabled_local_skill_ids.remove(skill_id)
                await skills_service.user_config.save_config(config)
                logger.info("Disabled local skill after uninstall: %s", skill_id)
        except Exception as e:
            logger.warning("Failed to disable local skill %s: %s", skill_id, e)


discovery_service = SkillDiscoveryService()
