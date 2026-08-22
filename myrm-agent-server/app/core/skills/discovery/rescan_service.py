"""Installed Skill Supply Chain Rescan Server Service.

Coordinates periodic and on-demand rescanning of installed skills,
governs user acknowledgment of security advisories,
and handles auto-quarantine/disabling of compromised skills.

[INPUT]
- myrm_agent_harness.backends.skills.scanning (POS: InstalledSkillRescanEngine, AdvisoryAckRegistry, SkillRescanResult)
- app.core.skills.store.service::skills_service (POS: installed skill listing and user config)
- app.services.event.app_event_bus::get_event_bus (POS: event broadcasting)

[OUTPUT]
- RescanReport: aggregated report across all scanned skills
- SkillRescanItem: per-skill rescan summary
- SkillRescanService: main service class
- rescan_service: singleton accessor

[POS]
Server-layer security coordinator for installed skills supply chain defense.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.agent.skills.market.service import LOCAL_INSTALL_DIR
from myrm_agent_harness.api import (
    AdvisoryAck,
    AdvisoryAckRegistry,
    InstalledSkillRescanEngine,
    SkillRescanResult,
)

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

_DEFAULT_ACKS_FILE = Path("~/.myrm/security_advisory_acks.json").expanduser()


@dataclass
class SkillRescanItem:
    """Summary item for one scanned skill."""

    skill_name: str
    recommendation: str
    is_clean: bool
    has_critical_or_malware: bool
    quarantined: bool
    summary: str
    declared_dependencies_count: int
    unacked_advisories_count: int
    acked_advisories_count: int
    findings_count: int


@dataclass
class RescanReport:
    """Aggregated report of a skill rescan execution."""

    total_scanned: int = 0
    clean_count: int = 0
    quarantined_count: int = 0
    items: list[SkillRescanItem] = field(default_factory=list)
    results: dict[str, SkillRescanResult] = field(default_factory=dict)


class SkillRescanService:
    """Server-side service coordinating installed skill rescans and advisory acks."""

    def __init__(
        self,
        engine: InstalledSkillRescanEngine | None = None,
        acks_file: Path | None = None,
    ) -> None:
        self._acks_file = acks_file or _DEFAULT_ACKS_FILE
        if engine is not None and getattr(engine, "ack_registry", None) is not None:
            self._registry = engine.ack_registry
        else:
            self._registry = AdvisoryAckRegistry()
            if self._acks_file.exists():
                self._registry.load_from_disk(self._acks_file)

        self._engine = engine or InstalledSkillRescanEngine(ack_registry=self._registry)
        self._last_report: RescanReport | None = None

    def get_last_report(self) -> RescanReport | None:
        """Get the last completed rescan report."""
        return self._last_report

    def ack_advisory(
        self,
        advisory_id: str,
        package_name: str,
        reason: str = "",
        acked_by: str = "user",
    ) -> AdvisoryAck:
        """Acknowledge / dismiss an advisory and persist to disk."""
        ack = self._registry.ack_advisory(advisory_id, package_name, reason, acked_by)
        self._registry.save_to_disk(self._acks_file)
        return ack

    def unack_advisory(self, advisory_id: str, package_name: str) -> bool:
        """Remove acknowledgment for an advisory and update disk."""
        res = self._registry.unack_advisory(advisory_id, package_name)
        if res:
            self._registry.save_to_disk(self._acks_file)
        return res

    def list_acks(self) -> list[AdvisoryAck]:
        """List all acknowledged advisories."""
        return self._registry.list_acks()

    async def rescan_skills(
        self,
        user_id: str = "default",
        skill_id: str | None = None,
        *,
        enable_online_osv: bool = True,
        auto_quarantine: bool = True,
    ) -> RescanReport:
        """Rescan installed skills and optionally quarantine compromised skills.

        Args:
            user_id: Active user ID for config updates.
            skill_id: Optional single skill name to rescan. If None, rescans all.
            enable_online_osv: Whether to query OSV API.
            auto_quarantine: Whether to disable/quarantine skills with critical vulnerabilities.

        Returns:
            RescanReport with detailed findings and disposition.
        """
        from app.core.skills.store.service import skills_service

        report = RescanReport()
        results: dict[str, SkillRescanResult] = {}

        if skill_id:
            target_dir = LOCAL_INSTALL_DIR / skill_id
            if target_dir.is_dir():
                res = await self._engine.rescan_skill_directory(
                    target_dir,
                    enable_online_osv=enable_online_osv,
                )
                results[skill_id] = res
        else:
            # Rescan all installed skills
            if LOCAL_INSTALL_DIR.is_dir():
                results = await self._engine.rescan_all_installed_skills(
                    LOCAL_INSTALL_DIR,
                    enable_online_osv=enable_online_osv,
                )

        quarantined_any = False
        for s_name, res in results.items():
            report.total_scanned += 1
            if res.is_clean:
                report.clean_count += 1

            quarantined = False
            if auto_quarantine and res.has_critical_or_malware:
                # Disable compromised skill to prevent execution
                try:
                    await skills_service.user_config.disable_local_skill(s_name)
                    quarantined = True
                    report.quarantined_count += 1
                    quarantined_any = True
                    logger.warning(
                        "Skill '%s' auto-quarantined due to supply chain threat: %s",
                        s_name,
                        res.summary,
                    )
                except Exception as exc:
                    logger.error("Failed to disable compromised skill %s: %s", s_name, exc)

            findings_count = (
                len(res.advisory_findings) + len(res.code_findings) + len(res.lifecycle_findings) + len(res.ast_findings)
            )

            report.items.append(
                SkillRescanItem(
                    skill_name=s_name,
                    recommendation=res.recommendation.value,
                    is_clean=res.is_clean,
                    has_critical_or_malware=res.has_critical_or_malware,
                    quarantined=quarantined,
                    summary=res.summary,
                    declared_dependencies_count=len(res.declared_dependencies),
                    unacked_advisories_count=len(res.unacked_advisory_findings),
                    acked_advisories_count=len(res.acked_advisory_findings),
                    findings_count=findings_count,
                )
            )

        report.results = results
        self._last_report = report

        # If any skills were quarantined, broadcast SKILL_POOL_UPDATED event
        if quarantined_any:
            try:
                bus = get_event_bus()
                await bus.publish(
                    AppEvent(
                        event_type=AppEventType.SKILL_POOL_UPDATED,
                        data={
                            "action": "quarantine",
                            "quarantined_count": report.quarantined_count,
                        },
                    )
                )
            except Exception as exc:
                logger.debug("Failed to broadcast SKILL_POOL_UPDATED event on quarantine: %s", exc)

        return report


rescan_service = SkillRescanService()
