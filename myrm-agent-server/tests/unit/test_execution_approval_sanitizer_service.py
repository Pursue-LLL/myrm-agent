"""
[POS] tests/unit/test_execution_approval_sanitizer_service.py
[INPUT] app.schemas.execution_approval_sanitizer, app.services.security.execution_approval_sanitizer_service
[OUTPUT] Unit tests for ExecutionApprovalSanitizerService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.execution_approval_sanitizer import (
    ApprovalSanitizeRequestDTO,
    QuickSanitizeRequestDTO,
)
from app.services.security.execution_approval_sanitizer_service import (
    ExecutionApprovalSanitizerService,
)


def test_service_sanitize_approval_payload() -> None:
    """Test full payload sanitization with findings and diagnostic badge."""
    service = ExecutionApprovalSanitizerService()

    raw_command = (
        'export OPENAI_API_KEY="sk-proj-1234567890abcdefghijklmnop" '
        '&& git clone https://ghp_123456789012345678901234567890123456@github.com/org/repo'
    )

    req = ApprovalSanitizeRequestDTO(
        request_id="req-test-01",
        session_id="sess-test-01",
        raw_command_or_text=raw_command,
        channel_target="slack",
    )

    res = service.sanitize_approval_payload(req)

    assert "sk-proj-1234567890abcdefghijklmnop" not in res.sanitized_text
    assert "ghp_123456789012345678901234567890123456" not in res.sanitized_text
    assert "[REDACTED:OPENAI_KEY]" in res.sanitized_text
    assert "[REDACTED:GITHUB_TOKEN]" in res.sanitized_text

    assert res.redactions_count == 2
    assert "OPENAI_API_KEY" in res.detected_secret_types
    assert "GITHUB_TOKEN" in res.detected_secret_types
    assert len(res.findings) == 2
    assert "已自动脱敏 2 处敏感凭据" in res.badge_summary


def test_service_quick_sanitize() -> None:
    """Test lightweight quick sanitize endpoint without session envelope."""
    service = ExecutionApprovalSanitizerService()

    raw = "connect redis://default:SuperSecretPassword123@redis.cache.internal:6379/0"
    req = QuickSanitizeRequestDTO(text=raw)

    res = service.quick_sanitize_text(req)

    assert "SuperSecretPassword123" not in res.sanitized_text
    assert "redis://default:[REDACTED:DB_PASSWORD]@redis.cache.internal:6379/0" in res.sanitized_text
    assert res.redactions_count == 1
    assert "DATABASE_PASSWORD" in res.detected_secret_types


def test_service_metrics() -> None:
    """Test metric tracking on clean and redacted payloads."""
    service = ExecutionApprovalSanitizerService()

    service.quick_sanitize_text(QuickSanitizeRequestDTO(text="echo hello world"))
    service.quick_sanitize_text(
        QuickSanitizeRequestDTO(text="export TOKEN=ghp_123456789012345678901234567890123456")
    )

    m = service.get_metrics()
    assert m.payloads_evaluated_total >= 2
    assert m.clean_payloads_total >= 1
    assert m.redacted_payloads_total >= 1
    assert m.total_secrets_redacted_count >= 1
