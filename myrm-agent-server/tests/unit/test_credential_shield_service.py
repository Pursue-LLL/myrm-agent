"""Unit test for CredentialShieldService.

[INPUT]
- AnalyzeCommandLineRequest, PipelineCommandRequest, SanitizeDisplayCommandRequest.

[OUTPUT]
- Verified behavior of CredentialShieldService methods.

[POS]
- Server unit test layer.
"""

from __future__ import annotations

from app.schemas.credential_shield import (
    AnalyzeCommandLineRequest,
    PipelineCommandRequest,
    SanitizeDisplayCommandRequest,
)
from app.services.security.credential_shield_service import (
    CredentialShieldService,
)


def test_service_analyze_command_detection() -> None:
    service = CredentialShieldService()

    # 1. Clean command
    res_clean = service.analyze_command(
        AnalyzeCommandLineRequest(command="curl https://api.myrm.dev/health")
    )
    assert res_clean.is_safe_for_process_table is True
    assert res_clean.risk_level == "SAFE"

    # 2. Curl command leaking Bearer token
    res_leak = service.analyze_command(
        AnalyzeCommandLineRequest(
            command="curl -sS -H 'Authorization: Bearer secret_live_key_9988' https://api.myrm.dev/v1"
        )
    )
    assert res_leak.is_safe_for_process_table is False
    assert res_leak.risk_level == "HIGH_RISK_PROCESS_TABLE_EXPOSURE"
    assert "HTTP_AUTH_HEADER_DETECTED" in res_leak.detected_leaks
    assert "[REDACTED_CREDENTIAL]" in (res_leak.suggested_rewritten_command or "")


def test_service_pipeline_command_and_sanitize_display() -> None:
    service = CredentialShieldService()

    # 1. Pipeline curl command
    raw_cmd = "curl -sS -H 'Authorization: Bearer secret_token_xyz' https://api.github.com/user"
    pipelined = service.pipeline_command(PipelineCommandRequest(command=raw_cmd))

    assert pipelined.transport_mode == "STDIN_CONFIG_STREAM"
    assert pipelined.has_stdin_payload is True
    assert "-K" in pipelined.sanitized_argv
    assert "-" in pipelined.sanitized_argv
    assert "secret_token_xyz" not in " ".join(pipelined.sanitized_argv)
    assert "[CREDENTIAL_VIA_STDIN_PIPELINE]" in pipelined.sanitized_display_cmd

    # 2. Sanitize display command
    sanitized = service.sanitize_display(
        SanitizeDisplayCommandRequest(
            command="my-cli --token my_sensitive_token_12345 --env prod"
        )
    )
    assert "my_sensitive_token_12345" not in sanitized.sanitized_command
    assert "[REDACTED_CREDENTIAL]" in sanitized.sanitized_command
