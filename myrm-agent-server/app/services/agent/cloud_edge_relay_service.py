"""Service implementation for Hybrid Cloud-Edge Sandbox Relay & Artifact Sync (Item 58).

[INPUT]
- RegisterArtifactRequest, AppendArtifactChunkRequest, DispatchLocalEgressRelayRequest,
  CompleteLocalEgressRelayRequest.

[OUTPUT]
- RegisterArtifactResponse, AppendArtifactChunkResponse, GetArtifactContentResponse,
  DispatchLocalEgressRelayResponse, CompleteLocalEgressRelayResponse, ListHybridArtifactsResponse.

[POS]
- Server-side business service bridging Harness HybridArtifactSyncEngine and
  CloudEdgeEgressRelayCoordinator to FastAPI routers.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from myrm_agent_harness.agent.sub_agents.cloud_edge_relay import (
    ArtifactSyncChunk,
    CloudEdgeEgressRelayCoordinator,
    HybridArtifactState,
    HybridArtifactSyncEngine,
    NetworkEgressStatusEnum,
    RelayNodeRoleEnum,
)

from app.schemas.cloud_edge_relay import (
    AppendArtifactChunkRequest,
    AppendArtifactChunkResponse,
    ArtifactSyncChunkDTO,
    CompleteLocalEgressRelayRequest,
    CompleteLocalEgressRelayResponse,
    DispatchLocalEgressRelayRequest,
    DispatchLocalEgressRelayResponse,
    GetArtifactContentResponse,
    HybridArtifactStateDTO,
    ListHybridArtifactsResponse,
    NetworkEgressStatusDTOEnum,
    RegisterArtifactRequest,
    RegisterArtifactResponse,
    RelayNodeRoleDTOEnum,
)

logger: Final = logging.getLogger(__name__)


def _map_role_dto_to_harness(role: RelayNodeRoleDTOEnum) -> RelayNodeRoleEnum:
    match role:
        case RelayNodeRoleDTOEnum.LOCAL_SANDBOX:
            return RelayNodeRoleEnum.LOCAL_SANDBOX
        case RelayNodeRoleDTOEnum.CLOUD_SANDBOX:
            return RelayNodeRoleEnum.CLOUD_SANDBOX
        case RelayNodeRoleDTOEnum.EDGE_GATEWAY:
            return RelayNodeRoleEnum.EDGE_GATEWAY


def _map_role_harness_to_dto(role: RelayNodeRoleEnum) -> RelayNodeRoleDTOEnum:
    match role:
        case RelayNodeRoleEnum.LOCAL_SANDBOX:
            return RelayNodeRoleDTOEnum.LOCAL_SANDBOX
        case RelayNodeRoleEnum.CLOUD_SANDBOX:
            return RelayNodeRoleDTOEnum.CLOUD_SANDBOX
        case RelayNodeRoleEnum.EDGE_GATEWAY:
            return RelayNodeRoleDTOEnum.EDGE_GATEWAY


def _map_status_harness_to_dto(status: NetworkEgressStatusEnum) -> NetworkEgressStatusDTOEnum:
    match status:
        case NetworkEgressStatusEnum.DIRECT_OK:
            return NetworkEgressStatusDTOEnum.DIRECT_OK
        case NetworkEgressStatusEnum.RELAY_REQUESTED:
            return NetworkEgressStatusDTOEnum.RELAY_REQUESTED
        case NetworkEgressStatusEnum.RELAY_COMPLETED:
            return NetworkEgressStatusDTOEnum.RELAY_COMPLETED
        case NetworkEgressStatusEnum.RELAY_FAILED:
            return NetworkEgressStatusDTOEnum.RELAY_FAILED


def _map_chunk_to_dto(chunk: ArtifactSyncChunk) -> ArtifactSyncChunkDTO:
    return ArtifactSyncChunkDTO(
        chunk_id=chunk.chunk_id,
        artifact_id=chunk.artifact_id,
        version=chunk.version,
        author_role=_map_role_harness_to_dto(chunk.author_role),
        content_delta=chunk.content_delta,
        row_count=chunk.row_count,
        timestamp=chunk.timestamp,
        checksum=chunk.checksum,
    )


def _map_state_to_dto(state: HybridArtifactState) -> HybridArtifactStateDTO:
    return HybridArtifactStateDTO(
        artifact_id=state.artifact_id,
        name=state.name,
        current_version=state.current_version,
        total_rows=state.total_rows,
        chunks=[_map_chunk_to_dto(c) for c in state.chunks],
        last_synced_at=state.last_synced_at,
        is_divergent=state.is_divergent,
    )


class CloudEdgeRelayService:
    """Coordinates hybrid artifact synchronizations and egress relay executions."""

    def __init__(self) -> None:
        self._sync_engine = HybridArtifactSyncEngine()
        self._egress_relay = CloudEdgeEgressRelayCoordinator()

    def register_artifact(self, request: RegisterArtifactRequest) -> RegisterArtifactResponse:
        """Initializes a shared hybrid artifact with baseline content."""
        harness_role = _map_role_dto_to_harness(request.author_role)
        state = self._sync_engine.register_artifact(
            artifact_id=request.artifact_id,
            name=request.name,
            initial_content=request.initial_content,
            initial_rows=request.initial_rows,
            author_role=harness_role,
        )
        logger.info(
            "Registered hybrid artifact '%s' (v%d, %d rows) for session '%s'",
            request.artifact_id,
            state.current_version,
            state.total_rows,
            request.session_id,
        )
        return RegisterArtifactResponse(
            success=True,
            state=_map_state_to_dto(state),
            message="Artifact registered successfully",
        )

    def append_chunk(self, request: AppendArtifactChunkRequest) -> AppendArtifactChunkResponse:
        """Appends an incremental delta to an artifact with optimistic CAS versioning."""
        harness_role = _map_role_dto_to_harness(request.author_role)
        try:
            state = self._sync_engine.append_chunk(
                artifact_id=request.artifact_id,
                content_delta=request.content_delta,
                author_role=harness_role,
                expected_version=request.expected_version,
                row_count=request.row_count,
            )
            return AppendArtifactChunkResponse(
                success=True,
                state=_map_state_to_dto(state),
                message=f"Appended chunk to v{state.current_version}",
            )
        except ValueError as err:
            logger.warning("CAS conflict on artifact '%s': %s", request.artifact_id, err)
            raise

    def get_artifact_state(self, artifact_id: str) -> HybridArtifactStateDTO:
        """Returns the current state of a tracked hybrid artifact."""
        state = self._sync_engine.get_artifact_state(artifact_id)
        return _map_state_to_dto(state)

    def get_aggregated_content(self, artifact_id: str) -> GetArtifactContentResponse:
        """Reconstructs the full content of an artifact across all sequential chunks."""
        state = self._sync_engine.get_artifact_state(artifact_id)
        content = self._sync_engine.get_aggregated_content(artifact_id)
        return GetArtifactContentResponse(
            artifact_id=state.artifact_id,
            name=state.name,
            current_version=state.current_version,
            total_rows=state.total_rows,
            aggregated_content=content,
        )

    def list_artifacts(self) -> ListHybridArtifactsResponse:
        """Lists all tracked hybrid artifacts."""
        all_artifacts = self._sync_engine.list_artifacts()
        dto_list = [_map_state_to_dto(st) for st in all_artifacts.values()]
        return ListHybridArtifactsResponse(artifacts=dto_list, total_count=len(dto_list))

    def get_provenance_summary(
        self, artifact_id: str
    ) -> Sequence[dict[str, str | int | float]]:
        """Returns the chronological provenance timeline for an artifact."""
        raw_summary = self._sync_engine.get_provenance_summary(artifact_id)
        return [dict(item) for item in raw_summary]

    def dispatch_local_egress_relay(
        self, request: DispatchLocalEgressRelayRequest
    ) -> DispatchLocalEgressRelayResponse:
        """Dispatches an outbound HTTP request through local network egress with SSRF checks."""
        source_role = _map_role_dto_to_harness(request.source_node)
        try:
            harness_req = self._egress_relay.create_relay_request(
                target_url=request.target_url,
                intent=request.intent,
                headers=request.headers,
                payload=request.payload,
                timeout_seconds=request.timeout_seconds,
                source_node=source_role,
            )
            return DispatchLocalEgressRelayResponse(
                relay_id=harness_req.relay_id,
                status=NetworkEgressStatusDTOEnum.RELAY_REQUESTED,
                extracted_data="",
                status_code=202,
                latency_ms=0.0,
                error_message="",
            )
        except ValueError as err:
            logger.warning(
                "SSRF or invalid host violation on URL '%s': %s",
                request.target_url,
                err,
            )
            raise

    def complete_local_egress_relay(
        self, request: CompleteLocalEgressRelayRequest
    ) -> CompleteLocalEgressRelayResponse:
        """Records the completion of an asynchronous egress relay task."""
        status = (
            NetworkEgressStatusEnum.RELAY_COMPLETED
            if request.status_code == 200
            else NetworkEgressStatusEnum.RELAY_FAILED
        )
        harness_resp = self._egress_relay.complete_relay_request(
            relay_id=request.relay_id,
            status=status,
            extracted_data=request.extracted_data,
            status_code=request.status_code,
            latency_ms=request.latency_ms,
            error_message=request.error_message,
        )
        return CompleteLocalEgressRelayResponse(
            relay_id=harness_resp.relay_id,
            status=_map_status_harness_to_dto(harness_resp.status),
            success=True,
        )

    def reset(self) -> None:
        """Resets engine state for testing isolation."""
        self._sync_engine.clear()
        self._egress_relay.clear()


_global_cloud_edge_relay_service: CloudEdgeRelayService | None = None


def get_cloud_edge_relay_service() -> CloudEdgeRelayService:
    """Returns singleton instance of CloudEdgeRelayService."""
    global _global_cloud_edge_relay_service
    if _global_cloud_edge_relay_service is None:
        _global_cloud_edge_relay_service = CloudEdgeRelayService()
    return _global_cloud_edge_relay_service
