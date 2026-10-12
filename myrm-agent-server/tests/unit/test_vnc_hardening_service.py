"""
[POS] tests/unit/test_vnc_hardening_service.py
[INPUT] app.schemas.vnc_hardening, app.services.security.vnc_hardening_service
[OUTPUT] Unit tests for VncHardeningService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.vnc_hardening import VncSecurityError

from app.schemas.vnc_hardening import (
    AuditRawVncCommandRequestDTO,
    EvaluatePasswordRequestDTO,
    GenerateSecurePasswordRequestDTO,
    SanitizeVncLaunchConfigRequestDTO,
)
from app.services.security.vnc_hardening_service import (
    VncHardeningService,
)


@pytest.fixture
def service() -> VncHardeningService:
    return VncHardeningService()


def test_sanitize_default_loopback_config(service: VncHardeningService) -> None:
    req = SanitizeVncLaunchConfigRequestDTO(
        display_num=0,
        vnc_port=5900,
        passwd_file="/var/secrets/vnc_pass",
        bind_mode="loopback",
    )
    spec = service.sanitize_launch_config(req)

    assert spec.is_hardened is True
    assert spec.effective_bind_mode == "loopback"
    assert "-localhost" in spec.command_args
    assert "-nopw" not in spec.command_args
    assert "-rfbauth" in spec.command_args
    assert "/var/secrets/vnc_pass" in spec.command_args


def test_sanitize_strips_conflicting_nopw(service: VncHardeningService) -> None:
    req = SanitizeVncLaunchConfigRequestDTO(
        display_num=1,
        vnc_port=5901,
        passwd_file="/var/secrets/vnc_pass",
        extra_flags=["-nopw", "-forever"],
        auto_remediate=True,
    )
    spec = service.sanitize_launch_config(req)

    assert "-nopw" not in spec.command_args
    assert "-forever" in spec.command_args
    assert "-localhost" in spec.command_args
    assert len(spec.violations) == 1
    assert spec.violations[0].violation_type == "nopw_conflict"
    assert spec.violations[0].auto_remediated is True


def test_sanitize_strict_mode_rejects_nopw(service: VncHardeningService) -> None:
    req = SanitizeVncLaunchConfigRequestDTO(
        display_num=1,
        vnc_port=5901,
        passwd_file="/var/secrets/vnc_pass",
        extra_flags=["-nopw"],
        auto_remediate=False,
    )
    with pytest.raises(VncSecurityError, match="Conflicting '-nopw' flag detected"):
        service.sanitize_launch_config(req)


def test_sanitize_non_loopback_opt_in_matrix(service: VncHardeningService) -> None:
    # 1. Non-loopback requested without explicit boolean flag
    req_unverified = SanitizeVncLaunchConfigRequestDTO(
        display_num=2,
        vnc_port=5902,
        passwd_file="/var/secrets/vnc_pass",
        bind_mode="non_loopback_opt_in",
        non_loopback_opt_in=False,
    )
    spec_unverified = service.sanitize_launch_config(req_unverified)
    assert spec_unverified.effective_bind_mode == "loopback"
    assert "-localhost" in spec_unverified.command_args

    # 2. Opt-in with strong password
    req_opt_in = SanitizeVncLaunchConfigRequestDTO(
        display_num=2,
        vnc_port=5902,
        passwd_file="/var/secrets/vnc_pass",
        bind_mode="non_loopback_opt_in",
        non_loopback_opt_in=True,
        opt_in_password="StrongPassword2026",
    )
    spec_opt_in = service.sanitize_launch_config(req_opt_in)
    assert spec_opt_in.effective_bind_mode == "non_loopback_opt_in"
    assert "-localhost" not in spec_opt_in.command_args
    assert len(spec_opt_in.violations) == 0


def test_audit_raw_command(service: VncHardeningService) -> None:
    # Insecure raw command missing localhost and having -nopw
    req_insecure = AuditRawVncCommandRequestDTO(
        command_args=["x11vnc", "-display", ":0", "-nopw"]
    )
    report = service.audit_raw_command(req_insecure)
    assert report.verdict == "BLOCKED"
    assert any(v.violation_type == "nopw_conflict" for v in report.spec.violations)
    assert any(v.violation_type == "unprotected_non_loopback" for v in report.spec.violations)


def test_password_generation_and_evaluation(service: VncHardeningService) -> None:
    # Generate password
    gen_res = service.generate_secure_password(GenerateSecurePasswordRequestDTO(length=18))
    assert len(gen_res.password) == 18

    # Evaluate strong password
    eval_strong = service.evaluate_password(EvaluatePasswordRequestDTO(password=gen_res.password))
    assert eval_strong.is_valid is True

    # Evaluate weak password
    eval_weak = service.evaluate_password(EvaluatePasswordRequestDTO(password="short"))
    assert eval_weak.is_valid is False
    assert "at least 8" in eval_weak.reason
