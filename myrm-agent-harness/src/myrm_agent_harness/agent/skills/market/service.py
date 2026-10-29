"""Skill market service.

Aggregates search results from multiple sources, orchestrates install flow.
Implements SkillMarketBackend protocol.

[INPUT]
- backends.skills.market_protocols::SkillInstallResult, (POS: SkillBackend SkillBackend SkillMarketBackend)
- backends.skills.scanning::ScanFinding, (POS: Scan result cache layer. Stores scan results in Volume (~/.myrm/skill_scans/) to avoid redundant scanning. Critical for performance: 20x speedup for repeat scans. Cache key: SHA256 hash of skill content Cache location: ~/.myrm/skill_scans/{content_hash}.json Expiration: 60 days TTL (auto-cleanup on get))
- .file_install::install_skill_files, resolve_install_error (POS: The one install path for an in-memory file tree, and the mapping of install errors to codes)
- .file_uninstall::uninstall_skill (POS: The one uninstall path, with cascade removal of a plugin's child skills)

[OUTPUT]
- EnrichedSearchResult: Search result enriched with local installation info.
- SkillPreviewResult: Preview result before installation (includes security scan).
- BaseSkillMarketService: Aggregates skill sources for search deduplication and qua...

[POS]
Skill market service.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.market.sanitizer import sanitize_skill_files
from myrm_agent_harness.backends.skills.market_protocols import (
    SkillInstallResult,
    SkillSearchResult,
)
from myrm_agent_harness.backends.skills.scanning import ScanFinding
from myrm_agent_harness.backends.skills.versioning import compare_versions

from .file_install import install_skill_files, resolve_install_error
from .file_uninstall import uninstall_skill
from .helpers import (
    SOURCE_PRIORITY,
    deduplicate,
    fetch_lobehub_as_skill,
    rank_results,
    scan_all_text_files,
)
from .installers.git_installer import GitInstaller
from .installers.zip_installer import ZipInstaller
from .sources.aliyun import AliyunSource
from .sources.base import SkillSource
from .sources.clawhub import ClawHubSource
from .sources.github import GitHubSkillSource
from .sources.lobehub import LobeHubSource
from .sources.modelscope import ModelScopeSource
from .sources.prebuilt import PrebuiltSkillSource
from .sources.skills_sh import SkillsShSource
from .sources.static_index import StaticIndexSkillSource

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.market_protocols import InstalledSkillStore

logger = logging.getLogger(__name__)

LOCAL_INSTALL_DIR = Path("~/.myrm/skills").expanduser()
SEARCH_TIMEOUT = 20.0
CACHE_MAX_ENTRIES = 100
CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class EnrichedSearchResult:
    """Search result enriched with local installation info."""

    result: SkillSearchResult
    installed_version: str = ""
    upgrade_available: bool = False


@dataclass(frozen=True)
class SkillPreviewResult:
    """Preview result before installation (includes security scan)."""

    skill_id: str
    name: str
    description: str
    version: str
    files: list[str]
    scan_findings: list[ScanFinding] = field(default_factory=list)
    is_clean: bool = True
    package_type: str = "skill"
    installed_skills: list[str] = field(default_factory=list)
    declared_mcp_servers: list[str] = field(default_factory=list)
    prerequisites: dict[str, object] | None = None
    """Prerequisite status report evaluating host OS, binaries, and Python dependencies."""


class BaseSkillMarketService:
    """Aggregates skill sources for search deduplication and quarantine-based install.
    Framework-layer service: does not depend on server database or event bus.
    """

    def __init__(
        self,
        github_token: str | None = None,
        skill_store: InstalledSkillStore | None = None,
    ) -> None:
        sources: list[SkillSource] = [
            StaticIndexSkillSource(),
            ClawHubSource(),
            GitHubSkillSource(token=github_token),
            SkillsShSource(),
            LobeHubSource(),
            ModelScopeSource(),
            AliyunSource(),
        ]
        if skill_store:
            sources.insert(0, PrebuiltSkillSource(skill_store))
        self._sources: list[SkillSource] = sources
        self._git_installer = GitInstaller()
        self._zip_installer = ZipInstaller()
        self._search_cache: dict[str, tuple[float, list[SkillSearchResult]]] = {}

    def register_source(self, source: SkillSource) -> None:
        """Register a custom skill source for search aggregation.

        Idempotent: skips if a source with the same source_name already exists.
        """
        if any(s.source_name == source.source_name for s in self._sources):
            return
        self._sources.append(source)
        logger.info("Registered custom skill source: %s", source.source_name)

    def unregister_source(self, source_name: str) -> bool:
        """Remove a custom skill source by name. Returns True if removed."""
        before = len(self._sources)
        self._sources = [s for s in self._sources if s.source_name != source_name]
        removed = len(self._sources) < before
        if removed:
            logger.info("Unregistered skill source: %s", source_name)
        return removed

    async def search(
        self,
        query: str,
        limit: int = 30,
        installed_versions_map: dict[str, str] | None = None,
    ) -> list[EnrichedSearchResult]:
        import time

        cache_key = query.lower().strip()
        is_browse = not cache_key
        now = time.time()

        raw_results: list[SkillSearchResult]
        cached = self._search_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            raw_results = cached[1][:limit]
        else:
            if is_browse:
                raw_results = []
            else:
                sources = self._sources

                async def _search_with_meta(
                    source_index: int, source: SkillSource
                ) -> tuple[int, str, list[SkillSearchResult]]:
                    results = await self._search_source(source, query, limit)
                    return source_index, source.source_name, results

                tasks = [_search_with_meta(source_index, source) for source_index, source in enumerate(sources)]
                source_batches: list[tuple[int, str, list[SkillSearchResult]]] = []
                for coro in asyncio.as_completed(tasks):
                    try:
                        source_batches.append(await asyncio.wait_for(coro, timeout=SEARCH_TIMEOUT))
                    except TimeoutError:
                        logger.warning("A skill source timed out during search")
                    except Exception as e:
                        logger.warning("Skill source search error: %s", e)

                source_batches.sort(
                    key=lambda batch: (
                        -SOURCE_PRIORITY.get(batch[1], 0),
                        batch[0],
                        batch[1],
                    )
                )
                all_results: list[SkillSearchResult] = []
                for _, _, source_results in source_batches:
                    all_results.extend(source_results)

                deduped = deduplicate(all_results)
                ranked = rank_results(deduped, query)
                raw_results = ranked[:limit]

            if len(self._search_cache) >= CACHE_MAX_ENTRIES:
                oldest_key = min(self._search_cache, key=lambda k: self._search_cache[k][0])
                del self._search_cache[oldest_key]
            self._search_cache[cache_key] = (now, raw_results)

        return self._enrich_results(raw_results, installed_versions_map)

    async def preview(self, skill_id: str, source: str) -> SkillPreviewResult:
        """Download skill content and run security scan without installing."""
        detail = await self.get_detail(skill_id, source)
        if not detail:
            raise ValueError(f"Skill not found: {skill_id} from {source}")

        if detail.install_method == "direct" and detail.source == "prebuilt":
            return SkillPreviewResult(
                skill_id=detail.id,
                name=detail.name,
                description=detail.description,
                version=detail.version,
                files=["SKILL.md"],
            )

        if detail.install_method == "git":
            skill_files = await self._git_installer.download(detail.install_url, detail.subdirectory)
        elif detail.install_method == "zip":
            skill_files = await self._zip_installer.download(detail.install_url, detail.subdirectory)
        else:
            raise ValueError(f"Unsupported install method: {detail.install_method}")

        scan_result = scan_all_text_files(detail.name, skill_files.files)

        package_type = "skill"
        installed_skills: list[str] = []
        declared_mcp_servers: list[str] = []
        if "plugin.json" in skill_files.files:
            package_type = "agent_plugin"
            try:
                from myrm_agent_harness.agent.plugins.parser import AgentPluginParser

                parser = AgentPluginParser()
                parsed = parser.parse_files(skill_files.files)
                installed_skills = [s.name for s in parsed.skills]
                declared_mcp_servers = [s.name for s in parsed.servers]
            except Exception as exc:
                logger.warning("Failed to parse plugin.json during preview: %s", exc)

        prerequisites_report: dict[str, object] | None = None
        try:
            from myrm_agent_harness.backends.skills.prerequisites import (
                check_skill_prerequisites,
            )

            req_data: dict[str, object] = {}
            if isinstance(detail.extra_manifest, dict):
                for section in ("requirements", "dependencies"):
                    declared = detail.extra_manifest.get(section)
                    if isinstance(declared, dict):
                        req_data.update(declared)
            if "requirements.json" in skill_files.files:
                import json

                try:
                    loaded_req = json.loads(skill_files.files["requirements.json"].decode("utf-8"))
                    if isinstance(loaded_req, dict):
                        req_data.update(loaded_req)
                except Exception:
                    pass

            if req_data:
                report = check_skill_prerequisites(detail.id, req_data)
                prerequisites_report = report.to_dict()
        except Exception as exc:
            logger.debug("Failed to evaluate prerequisites during preview: %s", exc)

        return SkillPreviewResult(
            skill_id=detail.id,
            name=skill_files.name,
            description=skill_files.description,
            version=detail.version,
            files=sorted(skill_files.files.keys()),
            scan_findings=list(scan_result.findings),
            is_clean=scan_result.is_clean,
            package_type=package_type,
            installed_skills=installed_skills or [skill_files.name],
            declared_mcp_servers=declared_mcp_servers,
            prerequisites=prerequisites_report,
        )

    async def install(
        self,
        skill_id: str,
        source: str,
        *,
        allow_downgrade: bool = False,
        progress_callback: Callable[[str, str, str], None] | None = None,
    ) -> SkillInstallResult:
        def _emit(stage: str, msg: str) -> None:
            if progress_callback:
                progress_callback(skill_id, stage, msg)

        _emit("resolving", "Resolving skill metadata...")
        detail = await self.get_detail(skill_id, source)
        if not detail:
            _emit("failed", "Skill not found")
            return SkillInstallResult(success=False, error=f"Skill not found: {skill_id} from {source}")

        if detail.install_method == "direct" and detail.source == "prebuilt":
            _emit("completed", "Prebuilt skill ready")
            return SkillInstallResult(
                success=True,
                skill_name=detail.name,
                skill_id=detail.id,
                installed_path="prebuilt (already installed)",
            )

        if detail.install_method == "direct" and detail.source == "lobehub":
            _emit("downloading", "Fetching LobeHub agent template...")
            try:
                files = await fetch_lobehub_as_skill(detail)
            except ValueError as e:
                resolved_error, error_code = resolve_install_error(e)
                _emit("failed", resolved_error)
                return SkillInstallResult(success=False, error=resolved_error, error_code=error_code)
            return await self.install_files(
                skill_id,
                detail.name,
                files,
                source=source,
                allow_downgrade=allow_downgrade,
                progress_callback=progress_callback,
            )

        _emit("downloading", f"Downloading from {source}...")
        try:
            if detail.install_method == "git":
                skill_files = await self._git_installer.download(detail.install_url, detail.subdirectory)
            elif detail.install_method == "zip":
                skill_files = await self._zip_installer.download(detail.install_url, detail.subdirectory)
            else:
                _emit("failed", "Unsupported install method")
                return SkillInstallResult(
                    success=False,
                    error=f"Unsupported install method: {detail.install_method}",
                )
        except ValueError as e:
            resolved_error, error_code = resolve_install_error(e)
            _emit("failed", resolved_error)
            return SkillInstallResult(success=False, error=resolved_error, error_code=error_code)

        sanitized = sanitize_skill_files(skill_files.files)
        return await self.install_files(
            skill_id,
            skill_files.name,
            sanitized,
            source=source,
            allow_downgrade=allow_downgrade,
            progress_callback=progress_callback,
        )

    async def install_from_url(
        self,
        url: str,
        *,
        allow_downgrade: bool = False,
        progress_callback: Callable[[str, str, str], None] | None = None,
    ) -> SkillInstallResult:
        from .sources.github import parse_github_url

        skill_id = f"url::{url[:80]}"

        def _emit(stage: str, msg: str) -> None:
            if progress_callback:
                progress_callback(skill_id, stage, msg)

        _emit("resolving", "Parsing URL...")

        try:
            ref = parse_github_url(url)
        except ValueError as e:
            _emit("failed", str(e))
            return SkillInstallResult(success=False, error=str(e))

        _emit("downloading", "Cloning repository...")
        try:
            skill_files = await self._git_installer.download(ref.clone_url, subdirectory=ref.subdirectory, ref=ref.ref)
        except ValueError as e:
            resolved_error, error_code = resolve_install_error(e)
            _emit("failed", resolved_error)
            return SkillInstallResult(success=False, error=resolved_error, error_code=error_code)

        sanitized = sanitize_skill_files(skill_files.files)
        return await self.install_files(
            skill_id,
            skill_files.name,
            sanitized,
            source="github",
            allow_downgrade=allow_downgrade,
            progress_callback=progress_callback,
        )

    async def uninstall(self, skill_id: str) -> SkillInstallResult:
        """Uninstall a locally installed skill and cascade-remove any child skills using receipt."""
        return await uninstall_skill(LOCAL_INSTALL_DIR, skill_id)

    async def get_detail(self, skill_id: str, source: str) -> SkillSearchResult | None:
        cached = self._find_in_cache(skill_id, source)
        if cached:
            return cached

        for src in self._sources:
            if src.source_name == source:
                return await src.get_detail(skill_id)
        return None

    def _find_in_cache(self, skill_id: str, source: str) -> SkillSearchResult | None:
        for _ts, results in self._search_cache.values():
            for r in results:
                if r.id == skill_id and r.source == source:
                    return r
        return None

    def _enrich_results(
        self,
        results: list[SkillSearchResult],
        installed_versions: dict[str, str] | None,
    ) -> list[EnrichedSearchResult]:
        if not installed_versions or not results:
            return [EnrichedSearchResult(result=r) for r in results]

        enriched: list[EnrichedSearchResult] = []
        for r in results:
            local_ver = installed_versions.get(r.name.lower(), "")
            if local_ver and r.version:
                delta = compare_versions(local_ver, r.version)
                enriched.append(
                    EnrichedSearchResult(
                        result=r,
                        installed_version=local_ver,
                        upgrade_available=delta.has_update,
                    )
                )
            elif local_ver:
                enriched.append(EnrichedSearchResult(result=r, installed_version=local_ver))
            else:
                enriched.append(EnrichedSearchResult(result=r))
        return enriched

    async def _search_source(self, source: SkillSource, query: str, limit: int) -> list[SkillSearchResult]:
        try:
            return await source.search(query, limit)
        except Exception as e:
            logger.warning("Search failed for source %s: %s", source.source_name, e)
            return []

    async def install_files(
        self,
        skill_id: str,
        name: str,
        files: dict[str, bytes],
        *,
        source: str = "",
        allow_downgrade: bool = False,
        progress_callback: Callable[[str, str, str], None] | None = None,
    ) -> SkillInstallResult:
        """Install an in-memory skill file tree through the quarantine pipeline (see ``install_skill_files``).

        Single install entry for every source that already holds the files (market downloads, LobeHub templates,
        Agent Plugin skills, business-layer imports). Rejections come back as failed results; unexpected errors
        propagate.
        """
        return await install_skill_files(
            LOCAL_INSTALL_DIR,
            skill_id,
            name,
            files,
            source=source,
            allow_downgrade=allow_downgrade,
            progress_callback=progress_callback,
        )
