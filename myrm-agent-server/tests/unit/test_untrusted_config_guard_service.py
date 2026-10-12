"""Unit tests for UntrustedConfigGuardService."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.untrusted_config_guard import (
    PreflightValidateRequest,
    ResolveConfigRequest,
)
from app.services.security.untrusted_config_guard_service import (
    UntrustedConfigGuardService,
)


def test_service_set_and_query_workspace_trust(tmp_path: Path) -> None:
    service = UntrustedConfigGuardService()
    ws_str = str(tmp_path)

    assert service.is_workspace_trusted(ws_str) is False

    service.set_workspace_trust(ws_str, True)
    assert service.is_workspace_trusted(ws_str) is True

    service.set_workspace_trust(ws_str, False)
    assert service.is_workspace_trusted(ws_str) is False


def test_service_resolve_untrusted_workspace(tmp_path: Path) -> None:
    service = UntrustedConfigGuardService()
    ws_dir = tmp_path / "untrusted_repo"
    ws_dir.mkdir()
    cfg_dir = ws_dir / ".myrm"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({
            "version": "1.0",
            "model_tier": "untrusted_compromised_override",
            "execution_timeout": 999.0,
        }),
        encoding="utf-8",
    )

    req = ResolveConfigRequest(
        workspace_path=str(ws_dir),
        is_project_trusted=False,
    )
    resp = service.resolve_config(req)

    # Invariant: Untrusted workspace local config is isolated and rejected
    assert resp.applied_tier == "local_project_untrusted_rejected"
    assert resp.effective_config.model_tier == "standard"
    assert resp.effective_config.execution_timeout == 30.0


def test_service_resolve_trusted_workspace(tmp_path: Path) -> None:
    service = UntrustedConfigGuardService()
    ws_dir = tmp_path / "trusted_repo"
    ws_dir.mkdir()
    cfg_dir = ws_dir / ".myrm"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({
            "version": "1.0",
            "model_tier": "trusted_team_override",
            "execution_timeout": 45.0,
        }),
        encoding="utf-8",
    )

    req = ResolveConfigRequest(
        workspace_path=str(ws_dir),
        is_project_trusted=True,
    )
    resp = service.resolve_config(req)

    assert resp.applied_tier == "local_project_trusted"
    assert resp.is_valid is True
    assert resp.effective_config.model_tier == "trusted_team_override"
    assert resp.effective_config.execution_timeout == 45.0


def test_service_validate_preflight() -> None:
    service = UntrustedConfigGuardService()

    # 1. Valid raw JSON
    valid_req = PreflightValidateRequest(
        raw_json=json.dumps({"version": "1.0", "description": "Good config"}),
    )
    res_valid = service.validate_preflight(valid_req)
    assert res_valid.is_valid is True
    assert res_valid.unknown_keys == []

    # 2. Unknown keys forbidden
    bad_req = PreflightValidateRequest(
        config_dict={
            "version": "1.0",
            "injected_unknown_key": "dangerous_payload",
        },
    )
    res_bad = service.validate_preflight(bad_req)
    assert res_bad.is_valid is False
    assert "injected_unknown_key" in res_bad.unknown_keys

    # 3. require_all_enabled assertion
    strict_req = PreflightValidateRequest(
        config_dict={
            "version": "1.0",
            "sandbox_enabled": False,
        },
        require_all_enabled=True,
    )
    res_strict = service.validate_preflight(strict_req)
    assert res_strict.is_valid is False
    assert res_strict.all_mandatory_features_enabled is False
