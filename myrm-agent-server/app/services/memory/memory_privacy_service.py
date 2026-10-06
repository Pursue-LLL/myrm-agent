"""
[POS] app/services/memory/memory_privacy_service.py
[INPUT] pathlib.Path, app/schemas/memory_privacy.py, myrm_agent_harness.toolkits.memory.privacy_gate
[OUTPUT] MemoryPrivacyService, get_memory_privacy_service

Service layer orchestrating memory privacy boundary gating, credential detection, and safe redaction.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from myrm_agent_harness.toolkits.memory.privacy_gate import (
    MemoryPrivacyBoundaryGate,
    MemoryPrivacyConfig,
    PrivacyCheckResult,
)

from app.schemas.memory_privacy import (
    PrivacyCheckRequestDTO,
    PrivacyCheckResponseDTO,
    PrivacyConfigDTO,
    SanitizeContentRequestDTO,
    SanitizeContentResponseDTO,
    SecretFindingDTO,
)


class MemoryPrivacyService:
    """Service wrapping memory privacy inspection and pre-commit secret scrubbing."""

    def __init__(self, gate: MemoryPrivacyBoundaryGate | None = None) -> None:
        if gate is not None:
            self._gate = gate
        else:
            ignore_file_env = os.getenv("MYRM_IGNORE_FILE", ".myrmignore")
            ignore_path = Path(ignore_file_env).resolve() if Path(ignore_file_env).exists() else None
            config = MemoryPrivacyConfig(
                block_on_critical=True,
                strict_mode=False,
            )
            self._gate = MemoryPrivacyBoundaryGate(config=config, ignore_file_path=ignore_path)

    def check(self, req: PrivacyCheckRequestDTO) -> PrivacyCheckResponseDTO:
        """Evaluate candidate text against memory privacy boundary policies."""
        result: PrivacyCheckResult = self._gate.check(
            content=req.content,
            source_path=req.source_path,
        )
        finding_dtos: list[SecretFindingDTO] = [
            SecretFindingDTO(
                violation_type=f.violation_type.value,
                snippet_masked=f.snippet_masked,
                category=f.category,
                line_number=f.line_number,
            )
            for f in result.findings
        ]
        return PrivacyCheckResponseDTO(
            passed=result.passed,
            sensitivity_level=result.sensitivity_level.value,
            findings=finding_dtos,
            redacted_content=result.redacted_content,
            violation_reason=result.violation_reason,
        )

    def sanitize(self, req: SanitizeContentRequestDTO) -> SanitizeContentResponseDTO:
        """Sanitize text by replacing secrets with semantic placeholders."""
        original = req.content
        sanitized = self._gate.sanitize(
            content=req.content,
            source_path=req.source_path,
        )
        return SanitizeContentResponseDTO(
            sanitized_content=sanitized,
            was_modified=(sanitized != original),
        )

    def get_config(self) -> PrivacyConfigDTO:
        """Return the active gate configuration with effective rules."""
        cfg = self._gate.config
        effective_exclude = list(self._gate.matcher._exclude_patterns)
        return PrivacyConfigDTO(
            allow_patterns=list(cfg.allow_patterns),
            exclude_patterns=effective_exclude,
            block_on_critical=cfg.block_on_critical,
            strict_mode=cfg.strict_mode,
        )


_MEMORY_PRIVACY_SERVICE_INSTANCE: MemoryPrivacyService | None = None
_MEMORY_PRIVACY_SERVICE_LOCK = threading.Lock()


def get_memory_privacy_service() -> MemoryPrivacyService:
    """Singleton provider for MemoryPrivacyService."""
    global _MEMORY_PRIVACY_SERVICE_INSTANCE
    if _MEMORY_PRIVACY_SERVICE_INSTANCE is None:
        with _MEMORY_PRIVACY_SERVICE_LOCK:
            if _MEMORY_PRIVACY_SERVICE_INSTANCE is None:
                _MEMORY_PRIVACY_SERVICE_INSTANCE = MemoryPrivacyService()
    return _MEMORY_PRIVACY_SERVICE_INSTANCE
