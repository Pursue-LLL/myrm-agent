"""
[POS] app/services/security/introspection_shield_service.py
[INPUT] pathlib, myrm_agent_harness.core.security.introspection_shield, app.schemas.introspection_shield
[OUTPUT] IntrospectionShieldService, get_introspection_shield_service

Domain service mediating requests for sandbox runtime introspection shielding
and decoupled workspace template hydration.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.core.security.introspection_shield import (
    HydratedTemplateRecord,
    IntrospectionShieldSuite,
    ProbeEvaluationResult,
)

from app.schemas.introspection_shield import (
    BlackholePatternsResponse,
    DecoupledTemplateStandardEnum,
    EvaluatePathProbeRequest,
    EvaluatePathProbeResponse,
    HydratedTemplateRecordResponse,
    HydrateTemplatesRequest,
    HydrateTemplatesResponse,
    IntrospectionProbeTypeEnum,
    IntrospectionShieldMetricsResponse,
    ScaffoldTemplatesRequest,
    ScaffoldTemplatesResponse,
    ShieldActionEnumResponse,
)


class IntrospectionShieldService:
    """Service orchestrating runtime introspection defense and workspace templates."""

    def __init__(self, suite: IntrospectionShieldSuite | None = None) -> None:
        self._suite = suite or IntrospectionShieldSuite()

    def evaluate_path(self, req: EvaluatePathProbeRequest) -> EvaluatePathProbeResponse:
        """Evaluate a file or directory access path against sandbox introspection blackholes."""
        workspace_root = Path(req.workspace_root) if req.workspace_root else None
        res: ProbeEvaluationResult = self._suite.evaluate_path(
            target_path=req.target_path,
            workspace_root=workspace_root,
        )

        probe_enum: IntrospectionProbeTypeEnum | None = None
        if res.probe_type is not None:
            probe_enum = IntrospectionProbeTypeEnum(res.probe_type.value)

        return EvaluatePathProbeResponse(
            is_blocked=res.is_blocked,
            probe_type=probe_enum,
            attempted_target=res.attempted_target,
            action_taken=ShieldActionEnumResponse(res.action_taken.value),
            sanitized_path=res.sanitized_path,
            explanation=res.explanation,
            timestamp=res.timestamp,
        )

    def hydrate_templates(self, req: HydrateTemplatesRequest) -> HydrateTemplatesResponse:
        """Discover and hydrate decoupled open standard templates from workspace root."""
        w_path = Path(req.workspace_dir)
        hydrated_map = self._suite.hydrate_workspace_templates(w_path)
        prompt_ctx = self._suite.build_prompt_context(hydrated_map)

        items: list[HydratedTemplateRecordResponse] = []
        total_chars = 0

        for record in hydrated_map.values():
            items.append(self._to_template_response(record))
            total_chars += record.character_count

        return HydrateTemplatesResponse(
            templates=items,
            prompt_context=prompt_ctx,
            total_characters=total_chars,
        )

    def scaffold_templates(self, req: ScaffoldTemplatesRequest) -> ScaffoldTemplatesResponse:
        """Scaffold baseline open standards workspace templates."""
        w_path = Path(req.workspace_dir)
        created = self._suite.scaffold_workspace_templates(w_path, overwrite=req.overwrite)
        return ScaffoldTemplatesResponse(
            workspace_dir=str(w_path),
            created_files=created,
        )

    def get_metrics(self) -> IntrospectionShieldMetricsResponse:
        """Fetch cumulative introspection shield operations metrics."""
        m = self._suite.metrics
        return IntrospectionShieldMetricsResponse(
            probes_evaluated=m.probes_evaluated,
            probes_blocked=m.probes_blocked,
            fake_root_redirects=m.fake_root_redirects,
            templates_hydrated=m.templates_hydrated,
            scaffolds_generated=m.scaffolds_generated,
        )

    def get_blackhole_patterns(self) -> BlackholePatternsResponse:
        """Fetch list of all active blackhole path patterns."""
        patterns = self._suite.get_blackhole_patterns()
        return BlackholePatternsResponse(
            patterns=list(patterns),
            count=len(patterns),
        )

    @staticmethod
    def _to_template_response(rec: HydratedTemplateRecord) -> HydratedTemplateRecordResponse:
        return HydratedTemplateRecordResponse(
            standard=DecoupledTemplateStandardEnum(rec.standard.value),
            filename=rec.filename,
            content=rec.content,
            source_path=rec.source_path,
            is_active=rec.is_active,
            character_count=rec.character_count,
        )


_default_service: IntrospectionShieldService | None = None


def get_introspection_shield_service() -> IntrospectionShieldService:
    """Dependency injection provider for IntrospectionShieldService."""
    global _default_service
    if _default_service is None:
        _default_service = IntrospectionShieldService()
    return _default_service
