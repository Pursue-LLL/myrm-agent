"""Vector space guard business service provider.

[POS]
Singleton service managing vector space model fingerprints, pre-flight safety
validations, space registration, and re-indexing workflows for Server API endpoints.

[INPUT]
- collections.abc.Sequence
- myrm_agent_harness.toolkits.vector (
    EmbeddingModelFingerprint,
    ReindexStatusReport,
    VectorSpaceGuard,
    VectorSpaceMetadata,
    VectorSpaceReindexer,
    VectorSpaceValidationResult,
  )
- app.schemas.space_guard (
    SpaceBindRequest,
    SpaceBindResponse,
    SpaceFingerprintDTO,
    SpaceReindexRequest,
    SpaceReindexResponse,
    SpaceStatusResponse,
    SpaceValidateRequest,
    SpaceValidateResponse,
  )

[OUTPUT]
- VectorSpaceGuardService, get_space_guard_service
"""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.toolkits.vector import (
    EmbeddingModelFingerprint,
    ReindexStatusReport,
    VectorSpaceGuard,
    VectorSpaceMetadata,
    VectorSpaceReindexer,
    VectorSpaceValidationResult,
)

from app.schemas.space_guard import (
    SpaceBindRequest,
    SpaceBindResponse,
    SpaceFingerprintDTO,
    SpaceReindexRequest,
    SpaceReindexResponse,
    SpaceStatusResponse,
    SpaceValidateRequest,
    SpaceValidateResponse,
)


class VectorSpaceGuardService:
    """Business service governing embedding model dimensions and vector space integrity."""

    def __init__(self, guard: VectorSpaceGuard | None = None) -> None:
        """Initialize service with underlying guard engine."""
        self._guard: VectorSpaceGuard = guard or VectorSpaceGuard()
        self._reindexer: VectorSpaceReindexer = VectorSpaceReindexer(self._guard)

    @property
    def guard(self) -> VectorSpaceGuard:
        """Access underlying vector space guard engine."""
        return self._guard

    @staticmethod
    def _to_harness_fingerprint(dto: SpaceFingerprintDTO) -> EmbeddingModelFingerprint:
        """Convert DTO to harness domain fingerprint model."""
        return EmbeddingModelFingerprint(
            provider_id=dto.provider_id,
            model_name=dto.model_name,
            vector_dimension=dto.vector_dimension,
            metric_type=dto.metric_type,
            config_hash=dto.config_hash,
        )

    @staticmethod
    def _to_dto_fingerprint(fp: EmbeddingModelFingerprint | None) -> SpaceFingerprintDTO | None:
        """Convert harness domain fingerprint model to DTO."""
        if fp is None:
            return None
        return SpaceFingerprintDTO(
            provider_id=fp.provider_id,
            model_name=fp.model_name,
            vector_dimension=fp.vector_dimension,
            metric_type=fp.metric_type,
            config_hash=fp.config_hash,
        )

    async def validate_space(self, request: SpaceValidateRequest) -> SpaceValidateResponse:
        """Validate whether current runtime model is compatible with collection space."""
        harness_fp = self._to_harness_fingerprint(request.fingerprint)
        res: VectorSpaceValidationResult = self._guard.validate_space(
            collection=request.collection,
            current_fingerprint=harness_fp,
            auto_bind_if_empty=request.auto_bind_if_empty,
        )
        return SpaceValidateResponse(
            is_valid=res.is_valid,
            status=res.status,
            message=res.message,
            recommended_action=res.recommended_action,
            expected_fingerprint=self._to_dto_fingerprint(res.expected_fingerprint),
            current_fingerprint=self._to_dto_fingerprint(res.current_fingerprint),
        )

    async def bind_space(self, request: SpaceBindRequest) -> SpaceBindResponse:
        """Bind or update model fingerprint space for target collection."""
        harness_fp = self._to_harness_fingerprint(request.fingerprint)
        meta: VectorSpaceMetadata = self._guard.bind_fingerprint(
            collection=request.collection,
            fingerprint=harness_fp,
            total_vectors_indexed=request.total_vectors_indexed,
        )
        return SpaceBindResponse(
            collection=meta.collection_name,
            fingerprint=self._to_dto_fingerprint(meta.fingerprint) or request.fingerprint,
            status="bound",
        )

    async def get_space_status(self, collection: str) -> SpaceStatusResponse:
        """Retrieve vector space metadata and diagnostic status."""
        meta = self._guard.get_space_metadata(collection)
        if meta is None:
            return SpaceStatusResponse(
                collection=collection,
                has_registered_space=False,
                fingerprint=None,
                total_vectors_indexed=0,
                last_validated_at=None,
            )
        return SpaceStatusResponse(
            collection=meta.collection_name,
            has_registered_space=True,
            fingerprint=self._to_dto_fingerprint(meta.fingerprint),
            total_vectors_indexed=meta.total_vectors_indexed,
            last_validated_at=meta.last_validated_at.isoformat(),
        )

    async def execute_reindex(self, request: SpaceReindexRequest) -> SpaceReindexResponse:
        """Execute space migration and re-indexing."""
        target_fp = self._to_harness_fingerprint(request.target_fingerprint)

        def _mock_reindex_embedder(items: Sequence[str]) -> Sequence[list[float]]:
            # Generates dummy vectors matching target dimension for reindex execution
            return [[0.0] * target_fp.vector_dimension for _ in items]

        try:
            report: ReindexStatusReport = await self._reindexer.execute_reindex(
                collection=request.collection,
                target_fingerprint=target_fp,
                items=request.sample_items,
                embedder=_mock_reindex_embedder,
            )
            return SpaceReindexResponse(
                collection=report.collection_name,
                status=report.status,
                reindexed_count=report.reindexed_count,
                error_message=report.error_message,
            )
        except Exception as exc:
            return SpaceReindexResponse(
                collection=request.collection,
                status="failed",
                reindexed_count=0,
                error_message=str(exc),
            )


_space_guard_service_instance: VectorSpaceGuardService | None = None


def get_space_guard_service() -> VectorSpaceGuardService:
    """Dependency injection provider returning singleton service instance."""
    global _space_guard_service_instance
    if _space_guard_service_instance is None:
        _space_guard_service_instance = VectorSpaceGuardService()
    return _space_guard_service_instance
