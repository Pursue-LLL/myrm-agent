"""Business-layer Skill Market Service.

Wraps the framework-layer BaseSkillMarketService to add:
- Integration with app.config.settings (e.g., GitHub token)
- SSE ServerEventBus progress emission
- Integration with installed versions

Post-install catalog enable is handled by discovery_mount (discovery API / autoupdate).
"""

import importlib
import logging
from typing import cast

from myrm_agent_harness.agent.skills.market.service import (
    BaseSkillMarketService,
    EnrichedSearchResult,
)
from myrm_agent_harness.agent.skills.market.sources.base import SkillSource
from myrm_agent_harness.agent.skills.market.sources.github import (
    GitHubRef,
    analyze_github_url,
)
from myrm_agent_harness.backends.skills.market_protocols import (
    InstalledSkillInfo,
    SkillInstallResult,
)

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
            InstalledSkillInfo(
                id=s.id,
                name=s.name,
                description=s.description,
                version=s.version,
                tags=s.tags,
            )
            for s in skills
        ]

    async def get_installed(self, skill_id: str) -> InstalledSkillInfo | None:
        from app.core.skills.store.service import skills_service

        skill = await skills_service.get_skill(skill_id)
        if not skill:
            return None
        return InstalledSkillInfo(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            tags=skill.tags,
        )


class SkillMarketService:
    def __init__(self) -> None:
        from app.config.settings import settings

        github_token = settings.services.github_token.get_secret_value() or None
        self._base = BaseSkillMarketService(
            github_token=github_token, skill_store=_AppSkillStore()
        )
        self._github_token = github_token
        self._clawhub_registry_applied = False
        self._register_custom_sources()

    def refresh_clawhub_source(self) -> None:
        """Reset ClawHub HTTP client and discovery search cache after registry URL changes."""
        for source in self._base._sources:
            if source.source_name != "clawhub":
                continue
            reset = getattr(source, "reset_client", None)
            if callable(reset):
                reset()
        self._base._search_cache.clear()

    async def ensure_clawhub_registry(self) -> None:
        if self._clawhub_registry_applied:
            return
        from myrm_agent_harness.agent.skills.market.sources.clawhub_registry import (
            migrate_legacy_registry_url,
        )

        from app.core.skills.clawhub_registry import (
            apply_clawhub_registry_url,
            normalize_clawhub_registry_url,
        )
        from app.core.skills.store.service import skills_service

        config = await skills_service.user_config.get_config()
        stored = (config.clawhub_registry_url or "").strip().rstrip("/")
        normalized = normalize_clawhub_registry_url(config.clawhub_registry_url)
        if stored and migrate_legacy_registry_url(stored) != stored:
            await skills_service.user_config.update_config(
                clawhub_registry_url=normalized,
            )
        apply_clawhub_registry_url(normalized)
        self._clawhub_registry_applied = True

    def _register_custom_sources(self) -> None:
        """Load persisted custom sources and register them into the base service."""
        from myrm_agent_harness.agent.skills.market.sources.wellknown import (
            WellKnownSkillSource,
        )

        from app.core.skills.custom_source_config import load_custom_sources

        config = load_custom_sources()
        for entry in config.sources:
            if entry.source_type == "well-known":
                try:
                    source = WellKnownSkillSource(entry.url)
                    self._base.register_source(source)
                except ValueError as e:
                    logger.warning(
                        "Skipping invalid custom source %s: %s", entry.url, e
                    )

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
            await self._base.search(
                query, limit=limit, installed_versions_map=installed_versions
            ),
        )

    async def install(
        self,
        skill_id: str,
        source: str,
    ) -> SkillInstallResult:
        def progress_callback(sid: str, stage: str, message: str) -> None:
            self._emit_progress(sid, stage, message)

        result = await self._base.install(
            skill_id, source, progress_callback=progress_callback
        )
        return result

    async def install_from_url(
        self,
        url: str,
    ) -> SkillInstallResult:
        def progress_callback(sid: str, stage: str, message: str) -> None:
            self._emit_progress(sid, stage, message)

        result = await self._base.install_from_url(
            url, progress_callback=progress_callback
        )
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
                full_url = (
                    f"{base}/tree/{r.ref}/{r.subdirectory}"
                    if (r.subdirectory and r.ref)
                    else base
                )
                description = ""

                # Fetch raw SKILL.md to get true name and description
                raw_base = f"https://raw.githubusercontent.com/{r.owner}/{r.repo}/{r.ref or 'HEAD'}"
                raw_path = (
                    f"{r.subdirectory}/SKILL.md" if r.subdirectory else "SKILL.md"
                )

                headers = {}
                if self._github_token:
                    headers["Authorization"] = f"token {self._github_token}"

                async with httpx.AsyncClient(timeout=5.0) as client:
                    try:
                        resp = await client.get(
                            f"{raw_base}/{raw_path}", headers=headers
                        )
                        if resp.status_code == 200:
                            content = resp.text
                            match = re.match(
                                r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL
                            )
                            if match:
                                yaml_mod = importlib.import_module("yaml")
                                frontmatter = yaml_mod.safe_load(match.group(1))
                                if isinstance(frontmatter, dict):
                                    name = str(frontmatter.get("name", name))
                                    description = str(
                                        frontmatter.get("description", description)
                                    )
                    except Exception as e:
                        logger.debug("Failed to fetch SKILL.md for %s: %s", raw_path, e)

                is_installed = name.lower() in installed_names
                return {
                    "url": full_url,
                    "name": name,
                    "description": description,
                    "is_installed": is_installed,
                }

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
            logger.warning(
                "Failed to fetch installed skills for version comparison: %s", e
            )
            return {}

    async def get_installed_local_ids_by_name(self) -> dict[str, str]:
        """Map installed local skill display name (lowercase) to canonical skill ID."""
        from app.core.skills.store.service import skills_service

        try:
            skills = await skills_service.list_skills()
            return {s.name.lower(): s.id for s in skills if s.id.startswith("local::")}
        except Exception as e:
            logger.warning("Failed to fetch installed local skill ids: %s", e)
            return {}

    def _emit_progress(self, skill_id: str, stage: str, message: str) -> None:
        from app.services.event.app_event_bus import (
            AppEvent,
            AppEventType,
            get_event_bus,
        )

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.SKILL_INSTALL_PROGRESS,
                data={"skill_id": skill_id, "stage": stage, "message": message},
            )
        )

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


market_service = SkillMarketService()
