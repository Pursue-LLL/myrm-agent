"""Server service for Zero-Trust Credential Isolation and Git Leakage Shield.

[INPUT]
- DTO requests from app.schemas.git_leak_shield
- Harness primitives: PreCommitSecretProbe, RedactedEgressFilter, EphemeralSecretVault

[OUTPUT]
- GitLeakShieldService: Orchestrates git diff inspection, commit gating, and egress redaction
- get_git_leak_shield_service: Singleton dependency provider

[POS]
Server security service. Protects users from leaking API keys and tokens during
coding agent Git operations or output generation.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.git_leak_shield import (
    EphemeralSecretVault,
    GitProbeResult,
    PreCommitSecretProbe,
    RedactedEgressFilter,
    RedactionResult,
    SecretMatch,
)

from app.schemas.git_leak_shield import (
    GitDiffScanRequest,
    GitDiffScanResponse,
    PreCommitCheckRequest,
    PreCommitCheckResponse,
    RedactTextRequest,
    RedactTextResponse,
    SecretMatchDto,
)

logger = logging.getLogger(__name__)


def _match_to_dto(m: SecretMatch) -> SecretMatchDto:
    return SecretMatchDto(
        secret_type=m.secret_type,
        pattern_name=m.pattern_name,
        line_number=m.line_number,
        masked_snippet=m.masked_snippet,
        suggested_env_var=m.suggested_env_var,
        file_path=m.file_path,
    )


class GitLeakShieldService:
    """Manages pre-commit leak scanning, git commit interception, and log redaction."""

    def __init__(self, vault: EphemeralSecretVault | None = None) -> None:
        self._vault = vault if vault is not None else EphemeralSecretVault()

    @property
    def vault(self) -> EphemeralSecretVault:
        """In-memory ephemeral vault reference."""
        return self._vault

    def scan_diff(self, request: GitDiffScanRequest) -> GitDiffScanResponse:
        """Inspect a git diff and return identified credential leaks."""
        result: GitProbeResult = PreCommitSecretProbe.scan_diff(
            diff_content=request.diff_content,
            file_path=request.file_path,
        )
        return GitDiffScanResponse(
            has_leak=result.has_leak,
            findings=[_match_to_dto(f) for f in result.findings],
            scanned_lines_count=result.scanned_lines_count,
            summary=result.summary,
        )

    def check_commit_command(self, request: PreCommitCheckRequest) -> PreCommitCheckResponse:
        """Verify whether a git commit/push command is safe to proceed."""
        is_git_target = PreCommitSecretProbe.is_git_commit_or_push(request.command)
        if not is_git_target:
            return PreCommitCheckResponse(
                blocked=False,
                reason="Command is not a git commit or git push operation; bypassed",
                findings=[],
            )

        if request.diff_content:
            diff_result = PreCommitSecretProbe.scan_diff(request.diff_content)
            if diff_result.has_leak:
                logger.warning(
                    "Blocked git operation '%s': detected %d secret leak(s)",
                    request.command,
                    len(diff_result.findings),
                )
                return PreCommitCheckResponse(
                    blocked=True,
                    reason=f"Git operation blocked: {len(diff_result.findings)} credential(s) detected in staging",
                    findings=[_match_to_dto(f) for f in diff_result.findings],
                )

        return PreCommitCheckResponse(
            blocked=False,
            reason="Git operation verified: zero credentials detected in staging",
            findings=[],
        )

    def redact_egress_text(self, request: RedactTextRequest) -> RedactTextResponse:
        """Redact sensitive credentials from text or log output."""
        result: RedactionResult = RedactedEgressFilter.redact_text(request.text)
        return RedactTextResponse(
            redacted_text=result.redacted_text,
            redactions_count=result.redactions_count,
            detected_types=result.detected_types,
        )


_global_git_leak_shield_service: GitLeakShieldService | None = None


def get_git_leak_shield_service() -> GitLeakShieldService:
    """Singleton getter for GitLeakShieldService."""
    global _global_git_leak_shield_service
    if _global_git_leak_shield_service is None:
        _global_git_leak_shield_service = GitLeakShieldService()
    return _global_git_leak_shield_service
