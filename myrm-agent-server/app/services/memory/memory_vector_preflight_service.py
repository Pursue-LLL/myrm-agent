"""
[POS] app/services/memory/memory_vector_preflight_service.py
[INPUT] logging, threading.Lock, myrm_agent_harness.toolkits.memory.vector_preflight, app.schemas.memory_vector_preflight
[OUTPUT] MemoryVectorPreflightService, get_memory_vector_preflight_service

Service providing vector store preflight connection endpoint sanitization and rigid dimension compatibility checking.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from threading import Lock

from myrm_agent_harness.toolkits.memory.vector_preflight import (
    DimensionIntegrityProbe,
    DimensionIntegrityReport,
    IPv4LoopbackSanitizer,
    SanitizedEndpointResult,
)

from app.schemas.memory_vector_preflight import (
    DimensionIntegrityReportDTO,
    InspectVectorStoreRequestDTO,
    InspectVectorStoreResponseDTO,
    SanitizeEndpointRequestDTO,
    SanitizeEndpointResponseDTO,
    VerifyDimensionsRequestDTO,
)

logger = logging.getLogger(__name__)


class MemoryVectorPreflightService:
    """Service mediating preflight sanitization and dimension assertion gates."""

    def __init__(self) -> None:
        self._lock: Lock = Lock()

    def sanitize_endpoint(
        self,
        request: SanitizeEndpointRequestDTO,
    ) -> SanitizeEndpointResponseDTO:
        """Sanitize an endpoint string to normalize localhost/IPv6 loopback to 127.0.0.1."""
        result: SanitizedEndpointResult = IPv4LoopbackSanitizer.sanitize_endpoint(request.endpoint)
        return SanitizeEndpointResponseDTO(
            raw_endpoint=result.raw_endpoint,
            sanitized_endpoint=result.sanitized_endpoint,
            was_modified=result.was_modified,
            modification_reason=result.modification_reason,
        )

    def verify_dimensions(
        self,
        request: VerifyDimensionsRequestDTO,
    ) -> DimensionIntegrityReportDTO:
        """Rigidly verify embedding model output dimensions against target collection requirement."""
        report: DimensionIntegrityReport = DimensionIntegrityProbe.verify_dimension_integrity(
            actual_dims=request.actual_dims,
            expected_dims=request.expected_dims,
            embedder_name=request.embedder_name,
            collection_name=request.collection_name,
        )
        return DimensionIntegrityReportDTO(
            is_valid=report.is_valid,
            actual_dims=report.actual_dims,
            expected_dims=report.expected_dims,
            status=report.status.value,
            diagnosis=report.diagnosis,
            suggested_action=report.suggested_action,
        )

    def inspect_vector_store(
        self,
        request: InspectVectorStoreRequestDTO,
    ) -> InspectVectorStoreResponseDTO:
        """Perform comprehensive combined preflight check for vector endpoint and dimensions."""
        endpoint_res = self.sanitize_endpoint(SanitizeEndpointRequestDTO(endpoint=request.endpoint))
        dim_report = self.verify_dimensions(
            VerifyDimensionsRequestDTO(
                actual_dims=request.actual_dims,
                expected_dims=request.expected_dims,
                embedder_name=request.embedder_name,
                collection_name=request.collection_name,
            )
        )

        overall_status = "ready"
        if not dim_report.is_valid:
            overall_status = "blocked"
        elif endpoint_res.was_modified:
            overall_status = "action_required_or_sanitized"

        logger.info(
            "Vector preflight check: endpoint=%s (modified=%s), dims=%d/%d (valid=%s), overall=%s",
            endpoint_res.sanitized_endpoint,
            endpoint_res.was_modified,
            dim_report.actual_dims,
            dim_report.expected_dims,
            dim_report.is_valid,
            overall_status,
        )

        return InspectVectorStoreResponseDTO(
            endpoint_result=endpoint_res,
            dimension_report=dim_report,
            overall_status=overall_status,
        )


_global_vector_preflight_service: MemoryVectorPreflightService | None = None
_preflight_service_lock: Lock = Lock()


def get_memory_vector_preflight_service() -> MemoryVectorPreflightService:
    """Singleton provider for MemoryVectorPreflightService."""
    global _global_vector_preflight_service
    if _global_vector_preflight_service is None:
        with _preflight_service_lock:
            if _global_vector_preflight_service is None:
                _global_vector_preflight_service = MemoryVectorPreflightService()
    return _global_vector_preflight_service
