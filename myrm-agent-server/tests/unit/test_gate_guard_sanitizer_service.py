"""Unit tests for GateGuardSanitizerService.

[INPUT]
- SanitizePathRequest, SanitizeReasonRequest, SanitizeDenialPayloadRequest.

[OUTPUT]
- Verified behavior of GateGuardSanitizerService layer.

[POS]
- Server unit test layer for GateGuard denial path Unicode sanitization (#3103).
"""

from __future__ import annotations

from app.schemas.gate_guard_sanitizer import (
    SanitizeDenialPayloadRequest,
    SanitizePathRequest,
    SanitizeReasonRequest,
)
from app.services.security.gate_guard_sanitizer_service import (
    GateGuardSanitizerService,
)


def test_service_sanitize_path_dangerous_unicode() -> None:
    service = GateGuardSanitizerService()
    req = SanitizePathRequest(
        path="/src/eu2028\u2028eu2029\u2029app.js\u200bhidden\u2060name\ufefftail\u3164x\u0091c1.js",
        max_length=500,
    )
    res = service.sanitize_path(req)

    for bad in ["\u2028", "\u2029", "\u200b", "\u2060", "\ufeff", "\u3164", "\u0091"]:
        assert bad not in res.sanitized_text

    assert "app.js" in res.sanitized_text
    assert "hidden" in res.sanitized_text
    assert res.has_modifications is True
    assert res.characters_removed_count >= 7
    assert "line_separator" in res.categories_detected
    assert "zero_width" in res.categories_detected
    assert res.was_truncated is False


def test_service_sanitize_clean_path() -> None:
    service = GateGuardSanitizerService()
    req = SanitizePathRequest(
        path="/usr/local/bin/deploy.sh",
        max_length=500,
    )
    res = service.sanitize_path(req)

    assert res.sanitized_text == "/usr/local/bin/deploy.sh"
    assert res.characters_removed_count == 0
    assert len(res.categories_detected) == 0
    assert res.has_modifications is False


def test_service_sanitize_reason() -> None:
    service = GateGuardSanitizerService()
    req = SanitizeReasonRequest(
        reason="Operation blocked: path contains \u202e dangerous extension",
        max_length=1000,
    )
    res = service.sanitize_reason(req)

    assert "\u202e" not in res.sanitized_text
    assert res.has_modifications is True
    assert "bidi_control" in res.categories_detected
    assert "Operation blocked: path contains" in res.sanitized_text


def test_service_sanitize_payload() -> None:
    service = GateGuardSanitizerService()
    req = SanitizeDenialPayloadRequest(
        tool_name="Execute\u200bCommand",
        target_path="/etc/\u200bpasswd",
        reason="Access to \u202epwd denied",
    )
    res = service.sanitize_denial_payload(req)

    assert res.tool_name == "Execute Command"
    assert res.target_path == "/etc/ passwd"
    assert "\u202e" not in res.reason
    assert res.has_modifications is True


def test_service_policy_summary() -> None:
    service = GateGuardSanitizerService()
    summary = service.get_policy_summary()

    assert summary.replacement_char == " "
    assert summary.max_path_length == 500
    assert summary.max_reason_length == 1000
    assert len(summary.supported_categories) >= 10
    assert "zero_width" in summary.supported_categories
    assert "bidi_control" in summary.supported_categories
