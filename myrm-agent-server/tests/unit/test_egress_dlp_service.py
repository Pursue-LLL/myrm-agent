"""Unit test for EgressDlpService.

[INPUT]
- ValidateEgressPolicyRequest, ScanDependenciesRequest, ScanProjectRequest.

[OUTPUT]
- Verified behavior of Egress DLP service methods.

[POS]
- Server unit test layer.
"""

from __future__ import annotations

from pathlib import Path

from app.schemas.egress_dlp import (
    EgressRuleDto,
    ScanDependenciesRequest,
    ScanProjectRequest,
    ValidateEgressPolicyRequest,
)
from app.services.security.egress_dlp_service import EgressDlpService


def test_service_validate_egress_rules() -> None:
    service = EgressDlpService()

    # Safe rules
    safe_req = ValidateEgressPolicyRequest(
        rules=[
            EgressRuleDto(destination="api.anthropic.com", port=443),
            EgressRuleDto(destination="api.openai.com", port=443),
        ],
    )
    res_safe = service.validate_egress_rules(safe_req)
    assert res_safe.is_safe is True
    assert res_safe.verdict == "ALLOWED"

    # Blocked rules
    bad_req = ValidateEgressPolicyRequest(
        rules=[
            EgressRuleDto(destination="api.openai.com", port=443),
            EgressRuleDto(destination="telemetry.crewai.com", port=443),
        ],
    )
    res_bad = service.validate_egress_rules(bad_req)
    assert res_bad.is_safe is False
    assert res_bad.verdict == "BLOCKED_TELEMETRY_DOMAIN"
    assert len(res_bad.detected_signatures) == 1
    assert res_bad.detected_signatures[0].framework_name == "CrewAI"

    # Exception bypass
    bad_req_exc = ValidateEgressPolicyRequest(
        rules=bad_req.rules,
        allowed_exceptions=["telemetry.crewai.com"],
    )
    res_exc = service.validate_egress_rules(bad_req_exc)
    assert res_exc.is_safe is True


def test_service_scan_dependencies_and_project(tmp_path: Path) -> None:
    service = EgressDlpService()

    # Clean dependencies
    clean_dep_req = ScanDependenciesRequest(
        manifest_content="httpx>=0.24.0\npytest>=8.0.0\n",
    )
    assert service.scan_dependencies(clean_dep_req).is_safe is True

    # Dirty dependencies
    dirty_dep_req = ScanDependenciesRequest(
        manifest_content="httpx>=0.24.0\nposthog>=3.0.0\n",
    )
    res_dirty = service.scan_dependencies(dirty_dep_req)
    assert res_dirty.is_safe is False
    assert res_dirty.verdict == "BLOCKED_TELEMETRY_DEPENDENCY"

    # Scan project directory
    proj_dir = tmp_path / "app_code"
    proj_dir.mkdir()
    code_file = proj_dir / "worker.py"
    code_file.write_text("import os\nprint('starting agent')\n", encoding="utf-8")

    proj_req = ScanProjectRequest(project_dir=str(proj_dir))
    assert service.scan_project(proj_req).is_safe is True

    # Signatures catalog
    signatures = service.list_signatures()
    assert len(signatures) >= 5
    assert any(s.target_domain == "posthog.com" for s in signatures)
