"""Service orchestrating cross-agent composable context projection, divergence arbitration, and handoff verification.

[INPUT]
- app.schemas.cross_agent_memory::* (POS: schemas)
- myrm_agent_harness.toolkits.memory.cross_agent.* (POS: harness engine)

[OUTPUT]
- CrossAgentMemoryService: Application service for cross-agent memory orchestration
- get_cross_agent_memory_service: FastAPI dependency provider

[POS]
Server-side bridge connecting multi-agent coordinator/UI and the harness cross-agent memory suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.memory.cross_agent.arbitrator import (
    MultiAgentConflictArbitrator,
)
from myrm_agent_harness.toolkits.memory.cross_agent.integrity import (
    HandoffIntegrityPipeline,
)
from myrm_agent_harness.toolkits.memory.cross_agent.projector import (
    ComposableContextProjector,
)
from myrm_agent_harness.toolkits.memory.cross_agent.types import (
    AgentMemoryDivergence,
    ArbitrationOutcome,
    ComposableContextProjection,
    HandoffPacket,
    HandoffVerificationResult,
    MemoryAssertion,
)

from app.schemas.cross_agent_memory import (
    ArbitrateConflictRequestDTO,
    ArbitrationOutcomeDTO,
    ComposableContextResponseDTO,
    ContextLayerDTO,
    HandoffPacketDTO,
    HandoffVerificationResponseDTO,
    MemoryAssertionDTO,
    ProjectComposableContextRequestDTO,
    SealHandoffRequestDTO,
    VerifyHandoffRequestDTO,
)

logger = logging.getLogger(__name__)


class CrossAgentMemoryService:
    """Provides application-layer execution of composable context, arbitration, and handoffs."""

    def __init__(
        self,
        projector: ComposableContextProjector | None = None,
        arbitrator: MultiAgentConflictArbitrator | None = None,
        integrity_pipeline: HandoffIntegrityPipeline | None = None,
    ) -> None:
        self.projector = projector or ComposableContextProjector()
        self.arbitrator = arbitrator or MultiAgentConflictArbitrator()
        self.integrity_pipeline = integrity_pipeline or HandoffIntegrityPipeline()

    def project_context(
        self, request: ProjectComposableContextRequestDTO
    ) -> ComposableContextResponseDTO:
        """Compose 4-layer virtual reference context preserving shared prefix cache."""
        projection: ComposableContextProjection = self.projector.project_for_agent(
            agent_id=request.agent_id,
            session_id=request.session_id,
            global_ground_truth=request.global_ground_truth,
            profile_tools_memory=request.profile_tools_memory,
            private_scratchpad=request.private_scratchpad,
            token_budget=request.token_budget,
        )

        layer_dtos = [
            ContextLayerDTO(
                layer_kind=layer.layer_kind.value,
                title=layer.title,
                content=layer.content,
                token_count=layer.token_count,
                content_hash=layer.content_hash,
                is_shared=layer.is_shared,
            )
            for layer in projection.layers
        ]

        return ComposableContextResponseDTO(
            agent_id=projection.agent_id,
            session_id=projection.session_id,
            total_tokens=projection.total_tokens,
            layers=layer_dtos,
            assembled_prompt_text=projection.assembled_prompt_text,
            cache_prefix_hash=projection.cache_prefix_hash,
        )

    def arbitrate_conflict(
        self, request: ArbitrateConflictRequestDTO
    ) -> ArbitrationOutcomeDTO:
        """Settle memory divergence between two agents using 3-tier deterministic arbitration."""
        runtime_arbitrator = self.arbitrator
        if request.workspace_root:
            runtime_arbitrator = MultiAgentConflictArbitrator(
                workspace_root=Path(request.workspace_root),
                coordinator_agent_ids=self.arbitrator.coordinator_agent_ids,
                confidence_delta_threshold=self.arbitrator.confidence_delta_threshold,
            )

        ast_a = MemoryAssertion(
            assertion_id=request.assertion_a.assertion_id,
            subject=request.assertion_a.subject,
            predicate=request.assertion_a.predicate,
            object_value=request.assertion_a.object_value,
            confidence=request.assertion_a.confidence,
            source_agent_id=request.assertion_a.source_agent_id,
            source_reference=request.assertion_a.source_reference,
            timestamp=request.assertion_a.timestamp or 0.0,
        )

        ast_b = MemoryAssertion(
            assertion_id=request.assertion_b.assertion_id,
            subject=request.assertion_b.subject,
            predicate=request.assertion_b.predicate,
            object_value=request.assertion_b.object_value,
            confidence=request.assertion_b.confidence,
            source_agent_id=request.assertion_b.source_agent_id,
            source_reference=request.assertion_b.source_reference,
            timestamp=request.assertion_b.timestamp or 0.0,
        )

        divergence = AgentMemoryDivergence(
            divergence_id=request.divergence_id or f"div-{request.subject[:8]}",
            subject=request.subject,
            predicate=request.predicate,
            agent_a_id=request.assertion_a.source_agent_id,
            assertion_a=ast_a,
            agent_b_id=request.assertion_b.source_agent_id,
            assertion_b=ast_b,
        )

        outcome: ArbitrationOutcome = runtime_arbitrator.arbitrate_divergence(divergence)

        winning_dto = MemoryAssertionDTO(
            assertion_id=outcome.winning_assertion.assertion_id,
            subject=outcome.winning_assertion.subject,
            predicate=outcome.winning_assertion.predicate,
            object_value=outcome.winning_assertion.object_value,
            confidence=outcome.winning_assertion.confidence,
            source_agent_id=outcome.winning_assertion.source_agent_id,
            source_reference=outcome.winning_assertion.source_reference,
            timestamp=outcome.winning_assertion.timestamp,
        )

        return ArbitrationOutcomeDTO(
            divergence_id=outcome.divergence_id,
            resolved=outcome.resolved,
            policy_applied=outcome.policy_applied.value,
            winning_assertion=winning_dto,
            audit_rationale=outcome.audit_rationale,
            requires_human_confirmation=outcome.requires_human_confirmation,
        )

    def seal_handoff(self, request: SealHandoffRequestDTO) -> HandoffPacketDTO:
        """Create a tamper-evident signed handoff packet."""
        assertions = [
            MemoryAssertion(
                assertion_id=a.assertion_id,
                subject=a.subject,
                predicate=a.predicate,
                object_value=a.object_value,
                confidence=a.confidence,
                source_agent_id=a.source_agent_id,
                source_reference=a.source_reference,
                timestamp=a.timestamp or 0.0,
            )
            for a in request.critical_assertions
        ]

        packet: HandoffPacket = self.integrity_pipeline.seal_handoff(
            source_agent_id=request.source_agent_id,
            target_agent_id=request.target_agent_id,
            task_id=request.task_id,
            context_snapshot=request.context_snapshot,
            assertions=assertions,
            secret_salt=request.secret_salt,
        )

        assertion_dtos = [
            MemoryAssertionDTO(
                assertion_id=a.assertion_id,
                subject=a.subject,
                predicate=a.predicate,
                object_value=a.object_value,
                confidence=a.confidence,
                source_agent_id=a.source_agent_id,
                source_reference=a.source_reference,
                timestamp=a.timestamp,
            )
            for a in packet.critical_assertions
        ]

        return HandoffPacketDTO(
            packet_id=packet.packet_id,
            source_agent_id=packet.source_agent_id,
            target_agent_id=packet.target_agent_id,
            task_id=packet.task_id,
            context_snapshot=packet.context_snapshot,
            critical_assertions=assertion_dtos,
            timestamp=packet.timestamp,
            signature_sha256=packet.signature_sha256,
        )

    def verify_handoff(
        self, request: VerifyHandoffRequestDTO
    ) -> HandoffVerificationResponseDTO:
        """Verify the integrity seal and assertions of an incoming handoff packet."""
        assertions = [
            MemoryAssertion(
                assertion_id=a.assertion_id,
                subject=a.subject,
                predicate=a.predicate,
                object_value=a.object_value,
                confidence=a.confidence,
                source_agent_id=a.source_agent_id,
                source_reference=a.source_reference,
                timestamp=a.timestamp,
            )
            for a in request.packet.critical_assertions
        ]

        packet = HandoffPacket(
            packet_id=request.packet.packet_id,
            source_agent_id=request.packet.source_agent_id,
            target_agent_id=request.packet.target_agent_id,
            task_id=request.packet.task_id,
            context_snapshot=request.packet.context_snapshot,
            critical_assertions=assertions,
            timestamp=request.packet.timestamp,
            signature_sha256=request.packet.signature_sha256,
        )

        res: HandoffVerificationResult = self.integrity_pipeline.verify_handoff(
            packet, secret_salt=request.secret_salt
        )

        return HandoffVerificationResponseDTO(
            packet_id=res.packet_id,
            is_valid=res.is_valid,
            verified_assertions_count=res.verified_assertions_count,
            rejection_reason=res.rejection_reason,
        )


_service_instance: CrossAgentMemoryService | None = None


def get_cross_agent_memory_service() -> CrossAgentMemoryService:
    """Dependency provider for CrossAgentMemoryService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CrossAgentMemoryService()
    return _service_instance
