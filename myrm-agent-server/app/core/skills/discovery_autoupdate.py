"""Skill auto-update checker.

Lazily checks for updates on installed skills by querying remote sources.
Does NOT perform in-place updates — returns update recommendations,
and the actual update goes through the quarantine install flow.

Strategy:
- check_updates() scans installed skills → queries matching sources → compares versions
- update_skill() re-installs via quarantine (download → scan → replace)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from myrm_agent_harness.backends.skills.discovery_protocols import SkillInstallResult
from myrm_agent_harness.backends.skills.versioning import VersionDelta, compare_versions

logger = logging.getLogger(__name__)

CHECK_COOLDOWN_SECONDS = 600


@dataclass(frozen=True, slots=True)
class SkillUpdateInfo:
    """Update availability info for one installed skill."""

    skill_name: str
    current_version: str
    remote_version: str
    source: str
    skill_id: str
    has_update: bool


@dataclass
class UpdateCheckResult:
    """Result of a batch update check."""

    checked_at: float = field(default_factory=time.time)
    updates: list[SkillUpdateInfo] = field(default_factory=list)

    @property
    def has_updates(self) -> bool:
        return any(u.has_update for u in self.updates)

    @property
    def available_updates(self) -> list[SkillUpdateInfo]:
        return [u for u in self.updates if u.has_update]


class SkillAutoUpdateChecker:
    """Lazy update checker with cooldown.

    Calls to check_updates() within the cooldown window return cached results.
    """

    def __init__(self) -> None:
        self._last_check: UpdateCheckResult | None = None

    async def check_updates(
        self,
        user_id: str,
        force: bool = False,
    ) -> UpdateCheckResult:
        """Check all installed skills for available updates.

        Args:
            user_id: User whose installed skills to check.
            force: Bypass cooldown and re-check immediately.
        """
        if not force and self._last_check:
            elapsed = time.time() - self._last_check.checked_at
            if elapsed < CHECK_COOLDOWN_SECONDS:
                return self._last_check

        from app.core.skills.discovery_service import discovery_service
        from app.core.skills.store.service import skills_service

        installed = await skills_service.list_skills()
        if not installed:
            result = UpdateCheckResult()
            self._last_check = result
            return result

        from myrm_agent_harness.agent.skills.discovery.helpers import read_origin
        from myrm_agent_harness.agent.skills.discovery.service import LOCAL_INSTALL_DIR

        non_prebuilt_sources = [s for s in discovery_service._sources if s.source_name != "prebuilt"]
        update_infos: list[SkillUpdateInfo] = []

        for skill in installed:
            if not skill.version or skill.version == "1.0.0":
                continue

            origin = read_origin(LOCAL_INSTALL_DIR / skill.name)
            origin_source = origin.get("source", "")

            sources_to_check = non_prebuilt_sources
            if origin_source:
                preferred = [s for s in non_prebuilt_sources if s.source_name == origin_source]
                if preferred:
                    sources_to_check = preferred

            for source in sources_to_check:
                try:
                    detail = await source.get_detail(skill.name)
                except Exception:
                    continue

                if not detail or not detail.version:
                    continue

                delta: VersionDelta = compare_versions(skill.version, detail.version)

                update_infos.append(
                    SkillUpdateInfo(
                        skill_name=skill.name,
                        current_version=skill.version,
                        remote_version=detail.version,
                        source=source.source_name,
                        skill_id=detail.id,
                        has_update=delta.has_update,
                    )
                )

                if delta.has_update:
                    break

        result = UpdateCheckResult(updates=update_infos)
        self._last_check = result
        return result

    async def update_skill(
        self,
        update_info: SkillUpdateInfo,
        user_id: str,
    ) -> SkillInstallResult:
        """Perform a non-inplace update via quarantine install flow.

        Downloads the new version → quarantine → security scan → replace.
        """
        from app.core.skills.discovery_service import discovery_service

        logger.debug("update_skill user=%s skill_id=%s", user_id, update_info.skill_id)
        return await discovery_service.install(
            skill_id=update_info.skill_id,
            source=update_info.source,
        )


_checker: SkillAutoUpdateChecker | None = None


def get_update_checker() -> SkillAutoUpdateChecker:
    """Singleton accessor."""
    global _checker  # noqa: PLW0603
    if _checker is None:
        _checker = SkillAutoUpdateChecker()
    return _checker
