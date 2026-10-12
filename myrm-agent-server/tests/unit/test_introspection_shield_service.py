"""
[POS] tests/unit/test_introspection_shield_service.py
[INPUT] pytest, tmp_path, pathlib, app.schemas.introspection_shield, app.services.security.introspection_shield_service
[OUTPUT] Unit tests for IntrospectionShieldService

Validates service-level path evaluation, blackhole shielding, fake-root redirection,
and decoupled template hydration and scaffolding.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

from app.schemas.introspection_shield import (
    DecoupledTemplateStandardEnum,
    EvaluatePathProbeRequest,
    HydrateTemplatesRequest,
    IntrospectionProbeTypeEnum,
    ScaffoldTemplatesRequest,
    ShieldActionEnumResponse,
)
from app.services.security.introspection_shield_service import (
    IntrospectionShieldService,
)


def test_service_evaluate_path_safe_and_blocked(tmp_path: Path) -> None:
    """Validate path evaluation distinguishing safe workspace files from introspection attacks."""
    service = IntrospectionShieldService()

    # 1. Safe path
    safe_req = EvaluatePathProbeRequest(
        target_path="app/main.py",
        workspace_root=str(tmp_path),
    )
    safe_res = service.evaluate_path(safe_req)
    assert not safe_res.is_blocked
    assert safe_res.action_taken == ShieldActionEnumResponse.ALLOW_UNRESTRICTED
    assert safe_res.probe_type is None

    # 2. Blocked host path probe (/opt/hatch)
    blocked_req = EvaluatePathProbeRequest(
        target_path="/opt/hatch/secret.yaml",
        workspace_root=str(tmp_path),
    )
    blocked_res = service.evaluate_path(blocked_req)
    assert blocked_res.is_blocked
    assert blocked_res.action_taken == ShieldActionEnumResponse.FAKE_ROOT_REDIRECT
    assert blocked_res.probe_type == IntrospectionProbeTypeEnum.HOST_PATH_PROBE
    assert "virtual_root/secret.yaml" in blocked_res.sanitized_path.replace("\\", "/")


def test_service_template_scaffolding_and_hydration(tmp_path: Path) -> None:
    """Validate scaffolding open standards templates and hydrating them into structured prompt context."""
    service = IntrospectionShieldService()

    # 1. Scaffold starter templates
    scaffold_req = ScaffoldTemplatesRequest(
        workspace_dir=str(tmp_path),
        overwrite=False,
    )
    scaffold_res = service.scaffold_templates(scaffold_req)
    assert len(scaffold_res.created_files) == 5
    assert "SOUL.md" in scaffold_res.created_files
    assert "USER.md" in scaffold_res.created_files

    # 2. Hydrate templates
    hydrate_req = HydrateTemplatesRequest(workspace_dir=str(tmp_path))
    hydrate_res = service.hydrate_templates(hydrate_req)
    assert len(hydrate_res.templates) == 5

    soul_record = next(t for t in hydrate_res.templates if t.standard == DecoupledTemplateStandardEnum.SOUL)
    assert soul_record.is_active is True
    assert soul_record.character_count > 0

    assert "<workspace_standards>" in hydrate_res.prompt_context
    assert "</workspace_standards>" in hydrate_res.prompt_context


def test_service_metrics_and_patterns() -> None:
    """Validate metrics and blackhole patterns retrieval."""
    service = IntrospectionShieldService()

    patterns_res = service.get_blackhole_patterns()
    assert patterns_res.count > 10
    assert "/opt/**" in patterns_res.patterns

    metrics = service.get_metrics()
    assert metrics.probes_evaluated >= 0
