"""Service layer for Structured JSON Scan Failure Errors.

[INPUT]
- EmitScanFailureRequest, ClassifyScanFailureRequest DTOs.

[OUTPUT]
- StructuredScanErrorEnvelopeDto, ClassifiedFailureDto.

[POS]
- Server service wrapping harness ScanFailureEmitter.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.structured_scan_errors.emitter import (
    ScanFailureEmitter,
)

from app.schemas.structured_scan_errors import (
    ClassifiedFailureDto,
    ClassifyScanFailureRequest,
    EmitScanFailureRequest,
    ScanErrorContextDto,
    ScanRemediationAdviceDto,
    StructuredScanErrorEnvelopeDto,
)


class StructuredScanErrorsService:
    """Classifies scan outputs and constructs standardized structured JSON error contracts."""

    def __init__(self, emitter: ScanFailureEmitter | None = None) -> None:
        self._emitter = emitter or ScanFailureEmitter()

    def emit_failure(
        self, request: EmitScanFailureRequest
    ) -> StructuredScanErrorEnvelopeDto:
        """Construct a full structured error envelope with context and remediation advice."""
        envelope = self._emitter.emit_failure(
            scan_id=request.scan_id,
            target_path_or_url=request.target_path_or_url,
            scanner_engine=request.scanner_engine,
            exit_code=request.exit_code,
            stderr=request.stderr,
            metadata=request.metadata,
        )

        ctx_dto = ScanErrorContextDto(
            scan_id=envelope.context.scan_id,
            target_path_or_url=envelope.context.target_path_or_url,
            scanner_engine=envelope.context.scanner_engine,
            exit_code=envelope.context.exit_code,
            timestamp=envelope.context.timestamp,
            raw_stderr_snippet=envelope.context.raw_stderr_snippet,
            metadata=envelope.context.metadata,
        )

        rem_dto = ScanRemediationAdviceDto(
            suggested_action=envelope.remediation.suggested_action.value,
            remediation_steps=list(envelope.remediation.remediation_steps),
            retryable=envelope.remediation.retryable,
            backoff_seconds=envelope.remediation.backoff_seconds,
        )

        return StructuredScanErrorEnvelopeDto(
            error_code=envelope.error_code.value,
            message=envelope.message,
            severity=envelope.severity,
            context=ctx_dto,
            remediation=rem_dto,
        )

    def classify_failure(
        self, request: ClassifyScanFailureRequest
    ) -> ClassifiedFailureDto:
        """Quickly classify raw stderr and exit code into error code and remediation action."""
        code, msg, action, steps, retryable, backoff = self._emitter.classify_failure(
            exit_code=request.exit_code,
            stderr=request.stderr,
        )

        return ClassifiedFailureDto(
            error_code=code.value,
            message=msg,
            suggested_action=action.value,
            remediation_steps=list(steps),
            retryable=retryable,
            backoff_seconds=backoff,
        )


_default_service: StructuredScanErrorsService | None = None


def get_structured_scan_errors_service() -> StructuredScanErrorsService:
    """Singleton provider for StructuredScanErrorsService."""
    global _default_service
    if _default_service is None:
        _default_service = StructuredScanErrorsService()
    return _default_service
