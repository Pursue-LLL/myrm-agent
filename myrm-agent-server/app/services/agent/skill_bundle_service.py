"""[INPUT] SkillBundleManifestDTO, RegisterBundleRequest, WarmupBundleRequest, ActivateBundleRequest.
[OUTPUT] SkillBundleService orchestrating batch bundle packaging, pre-flight warmup, and session activation.
[POS] Service layer for Skill Bundles Batch Manifest & Lifecycle Warmup Manager (Item 41).
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.skills.bundle_warmup import (
    BundleActivationRecord,
    BundleCategory,
    BundleSkillSpec,
    BundleWarmupCheck,
    BundleWarmupReport,
    SkillBundleLifecycleManager,
    SkillBundleManifest,
)

from app.schemas.skill_bundle import (
    BundleActivationRecordDTO,
    BundleCategoryEnum,
    BundleSkillSpecDTO,
    BundleWarmupCheckDTO,
    BundleWarmupReportDTO,
    SkillBundleManifestDTO,
    WarmupStatusEnum,
)

logger = logging.getLogger(__name__)


def _skill_spec_to_dto(spec: BundleSkillSpec) -> BundleSkillSpecDTO:
    return BundleSkillSpecDTO(
        skill_id=spec.skill_id,
        name=spec.name,
        description=spec.description,
        required_env_vars=list(spec.required_env_vars),
        required_tools=list(spec.required_tools),
        is_optional=spec.is_optional,
    )


def _skill_spec_from_dto(dto: BundleSkillSpecDTO) -> BundleSkillSpec:
    return BundleSkillSpec(
        skill_id=dto.skill_id,
        name=dto.name,
        description=dto.description,
        required_env_vars=list(dto.required_env_vars),
        required_tools=list(dto.required_tools),
        is_optional=dto.is_optional,
    )


def _check_to_dto(c: BundleWarmupCheck) -> BundleWarmupCheckDTO:
    return BundleWarmupCheckDTO(
        check_name=c.check_name,
        status=WarmupStatusEnum(c.status.value),
        message=c.message,
        is_resolved=c.is_resolved,
    )


def _report_to_dto(r: BundleWarmupReport) -> BundleWarmupReportDTO:
    return BundleWarmupReportDTO(
        bundle_id=r.bundle_id,
        overall_status=WarmupStatusEnum(r.overall_status.value),
        checks=[_check_to_dto(c) for c in r.checks],
        checked_at=r.checked_at,
    )


def _manifest_to_dto(m: SkillBundleManifest) -> SkillBundleManifestDTO:
    return SkillBundleManifestDTO(
        bundle_id=m.bundle_id,
        name=m.name,
        description=m.description,
        category=BundleCategoryEnum(m.category.value),
        skills=[_skill_spec_to_dto(s) for s in m.skills],
        author=m.author,
        version=m.version,
        tags=list(m.tags),
        created_at=m.created_at,
    )


def _manifest_from_dto(dto: SkillBundleManifestDTO) -> SkillBundleManifest:
    return SkillBundleManifest(
        bundle_id=dto.bundle_id,
        name=dto.name,
        description=dto.description,
        category=BundleCategory(dto.category.value),
        skills=[_skill_spec_from_dto(s) for s in dto.skills],
        author=dto.author,
        version=dto.version,
        tags=list(dto.tags),
        created_at=dto.created_at,
    )


def _record_to_dto(rec: BundleActivationRecord) -> BundleActivationRecordDTO:
    return BundleActivationRecordDTO(
        session_id=rec.session_id,
        bundle_id=rec.bundle_id,
        activated_skills=list(rec.activated_skills),
        warmup_status=WarmupStatusEnum(rec.warmup_status.value),
        activated_at=rec.activated_at,
    )


class SkillBundleService:
    """Service mediating scenario-based skill bundles, warmup probes, and atomic activations."""

    def __init__(self) -> None:
        self._manager = SkillBundleLifecycleManager(include_defaults=True)
        self._lock = threading.Lock()

    def register_bundle(self, dto: SkillBundleManifestDTO) -> SkillBundleManifestDTO:
        with self._lock:
            domain_manifest = _manifest_from_dto(dto)
            registered = self._manager.register_bundle(domain_manifest)
            logger.info("Registered skill bundle '%s' (%s)", registered.bundle_id, registered.name)
            return _manifest_to_dto(registered)

    def get_bundle(self, bundle_id: str) -> SkillBundleManifestDTO | None:
        with self._lock:
            bundle = self._manager.get_bundle(bundle_id)
            if bundle is None:
                return None
            return _manifest_to_dto(bundle)

    def list_bundles(
        self, category: BundleCategoryEnum | None = None
    ) -> list[SkillBundleManifestDTO]:
        with self._lock:
            domain_cat = BundleCategory(category.value) if category else None
            bundles = self._manager.list_bundles(domain_cat)
            return [_manifest_to_dto(b) for b in bundles]

    def warmup_bundle(
        self,
        bundle_id: str,
        available_skills: list[str],
        env_vars: dict[str, str],
        available_tools: list[str] | None = None,
    ) -> BundleWarmupReportDTO:
        with self._lock:
            skills_set = set(available_skills)
            tools_set = set(available_tools) if available_tools is not None else None
            report = self._manager.warmup_bundle(
                bundle_id=bundle_id,
                available_skills=skills_set,
                env_vars=env_vars,
                available_tools=tools_set,
            )
            logger.info(
                "Warmup probe for bundle '%s' evaluated status: %s",
                bundle_id,
                report.overall_status,
            )
            return _report_to_dto(report)

    def activate_bundle(
        self,
        session_id: str,
        bundle_id: str,
        available_skills: list[str],
        env_vars: dict[str, str],
        force: bool = False,
    ) -> BundleActivationRecordDTO:
        with self._lock:
            record = self._manager.activate_bundle(
                session_id=session_id,
                bundle_id=bundle_id,
                available_skills=set(available_skills),
                env_vars=env_vars,
                force=force,
            )
            logger.info(
                "Activated bundle '%s' for session '%s' (status: %s)",
                bundle_id,
                session_id,
                record.warmup_status,
            )
            return _record_to_dto(record)

    def deactivate_bundle(self, session_id: str, bundle_id: str) -> bool:
        with self._lock:
            deactivated = self._manager.deactivate_bundle(session_id, bundle_id)
            logger.info("Deactivated bundle '%s' for session '%s': %s", bundle_id, session_id, deactivated)
            return deactivated

    def get_session_activations(self, session_id: str) -> list[BundleActivationRecordDTO]:
        with self._lock:
            records = self._manager.get_session_activations(session_id)
            return [_record_to_dto(r) for r in records]


_global_skill_bundle_service = SkillBundleService()


def get_skill_bundle_service() -> SkillBundleService:
    """Retrieve global singleton SkillBundleService instance."""
    return _global_skill_bundle_service
