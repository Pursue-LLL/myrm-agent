"""
[POS] app/services/memory/memory_drift_service.py
[INPUT] myrm_agent_harness.toolkits.memory.drift_defense, app/schemas/memory_drift.py
[OUTPUT] MemoryDriftService, get_memory_drift_service

Business service mediating pre-injection ground truth drift detection and stale warnings.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

from myrm_agent_harness.toolkits.memory.drift_defense import (
    DriftCheckRequest,
    DriftCheckResult,
    DriftDefenseConfig,
    GroundTruthDriftDetector,
    StaleMemoryDecorator,
)

from app.schemas.memory_drift import (
    BatchDriftCheckRequestDTO,
    BatchDriftCheckResponseDTO,
    DriftCheckRequestDTO,
    DriftCheckResponseDTO,
    MemoryDriftFindingDTO,
)

logger = logging.getLogger(__name__)


class MemoryDriftService:
    """Service evaluating memory candidates against real repository / workspace ground truth."""

    def __init__(
        self,
        detector: GroundTruthDriftDetector | None = None,
        decorator: StaleMemoryDecorator | None = None,
        default_workspace_root: Path | str | None = None,
    ) -> None:
        self._detector = detector or GroundTruthDriftDetector(config=DriftDefenseConfig())
        self._decorator = decorator or StaleMemoryDecorator()
        self._default_workspace = Path(default_workspace_root or Path.cwd()).resolve()
        logger.info("MemoryDriftService initialized with default_workspace=%s", self._default_workspace)

    def check(self, request: DriftCheckRequestDTO) -> DriftCheckResponseDTO:
        """Inspect a single candidate memory for ground truth drift."""
        ws_root = Path(request.workspace_root).resolve() if request.workspace_root else self._default_workspace
        harness_req = DriftCheckRequest(
            memory_id=request.memory_id,
            content=request.content,
            workspace_root=ws_root,
            recorded_path=request.recorded_path,
            recorded_symbol=request.recorded_symbol,
        )

        result: DriftCheckResult = self._detector.check(harness_req)

        return DriftCheckResponseDTO(
            memory_id=result.memory_id,
            is_drifted=result.is_drifted,
            confidence_penalty=result.confidence_penalty,
            findings=[
                MemoryDriftFindingDTO(
                    drift_type=f.drift_type.value if hasattr(f.drift_type, "value") else str(f.drift_type),
                    reference_target=f.reference_target,
                    detail=f.detail,
                    is_stale=f.is_stale,
                )
                for f in result.findings
            ],
            decorated_content=result.decorated_content,
        )

    def check_batch(self, request: BatchDriftCheckRequestDTO) -> BatchDriftCheckResponseDTO:
        """Inspect a batch of candidate memories for physical drift."""
        outcomes: list[DriftCheckResponseDTO] = []
        drifted_count = 0

        fallback_ws = request.workspace_root

        for item in request.items:
            # Inherit batch-level workspace root if item does not specify its own
            resolved_item = item.model_copy()
            if not resolved_item.workspace_root and fallback_ws:
                resolved_item.workspace_root = fallback_ws

            dto = self.check(resolved_item)
            if dto.is_drifted:
                drifted_count += 1
            outcomes.append(dto)

        return BatchDriftCheckResponseDTO(
            results=outcomes,
            total_checked=len(outcomes),
            drifted_count=drifted_count,
        )


_service_lock = Lock()
_service_instance: MemoryDriftService | None = None


def get_memory_drift_service() -> MemoryDriftService:
    """Singleton provider for MemoryDriftService."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = MemoryDriftService()
    return _service_instance
