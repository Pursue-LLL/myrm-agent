"""Unit test for StructuredScanErrorsService.

[INPUT]
- EmitScanFailureRequest, ClassifyScanFailureRequest.

[OUTPUT]
- Verified behavior of structured scan failure emission and fast classification.

[POS]
- Server unit test layer for structured JSON scan failure errors.
"""

from __future__ import annotations

from app.schemas.structured_scan_errors import (
    ClassifyScanFailureRequest,
    EmitScanFailureRequest,
)
from app.services.security.structured_scan_errors_service import (
    StructuredScanErrorsService,
)


def test_service_emit_failure() -> None:
    service = StructuredScanErrorsService()

    req = EmitScanFailureRequest(
        scan_id="scan-unit-001",
        target_path_or_url="/repos/my-web-app",
        scanner_engine="semgrep",
        exit_code=137,
        stderr="Process killed by OOM killer (exit code 137)",
        metadata={"job_id": "gh-actions-999"},
    )
    envelope = service.emit_failure(req)

    assert envelope.error_code == "SCAN_OUT_OF_MEMORY"
    assert envelope.severity == "CRITICAL"
    assert envelope.remediation.suggested_action == "RETRY"
    assert envelope.remediation.retryable is True
    assert envelope.context.scan_id == "scan-unit-001"
    assert envelope.context.metadata["job_id"] == "gh-actions-999"


def test_service_classify_failure() -> None:
    service = StructuredScanErrorsService()

    # 1. Rate limited
    res_rl = service.classify_failure(
        ClassifyScanFailureRequest(
            exit_code=1,
            stderr="HTTP 429 Too Many Requests: vulnerability feed rate limit reached",
        )
    )
    assert res_rl.error_code == "SCAN_RATE_LIMITED"
    assert res_rl.suggested_action == "RETRY"
    assert res_rl.retryable is True
    assert res_rl.backoff_seconds == 60.0

    # 2. Syntax error in ruleset
    res_syntax = service.classify_failure(
        ClassifyScanFailureRequest(
            exit_code=2,
            stderr="Syntax error: invalid yaml structure in rules/custom.yaml",
        )
    )
    assert res_syntax.error_code == "SCAN_RULESET_SYNTAX_ERROR"
    assert res_syntax.suggested_action == "BLOCK_PIPELINE"
    assert res_syntax.retryable is False
