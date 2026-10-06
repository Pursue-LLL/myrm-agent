"""
[POS] app/services/memory/memory_provenance_batch_service.py
[INPUT] app.schemas.memory_provenance_batch, myrm_agent_harness.toolkits.memory.provenance_batch
[OUTPUT] MemoryProvenanceBatchService, get_memory_provenance_batch_service

Service coordinating skill memory provenance tracing and batch learning namespace isolation.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.provenance_batch import (
    BatchLearnItem,
    BatchLearnNamespaceIsolator,
    ExtractionProvenanceLink,
    SkillProvenanceLinker,
    ToolExecutionTrace,
)

from app.schemas.memory_provenance_batch import (
    BatchLearnItemDTO,
    BatchLearnRequestDTO,
    BatchLearnResponseDTO,
    CreateProvenanceLinkRequestDTO,
    ExtractionProvenanceLinkDTO,
    NamespacedMemoryRefDTO,
    ToolExecutionTraceDTO,
)


def _to_harness_trace(dto: ToolExecutionTraceDTO) -> ToolExecutionTrace:
    """Convert API ToolExecutionTraceDTO to harness ToolExecutionTrace."""
    return ToolExecutionTrace(
        tool_name=dto.tool_name,
        tool_call_id=dto.tool_call_id,
        input_args_summary=dto.input_args_summary,
        output_evidence_snippet=dto.output_evidence_snippet,
        status=dto.status,
        duration_ms=dto.duration_ms,
    )


def _to_dto_trace(harness: ToolExecutionTrace) -> ToolExecutionTraceDTO:
    """Convert harness ToolExecutionTrace to API ToolExecutionTraceDTO."""
    return ToolExecutionTraceDTO(
        tool_name=harness.tool_name,
        tool_call_id=harness.tool_call_id,
        input_args_summary=harness.input_args_summary,
        output_evidence_snippet=harness.output_evidence_snippet,
        status=harness.status,
        duration_ms=harness.duration_ms,
    )


def _to_harness_link(dto: ExtractionProvenanceLinkDTO) -> ExtractionProvenanceLink:
    """Convert API ExtractionProvenanceLinkDTO to harness ExtractionProvenanceLink."""
    return ExtractionProvenanceLink(
        link_id=dto.link_id,
        conversation_id=dto.conversation_id,
        turn_index=dto.turn_index,
        trigger_prompt_snippet=dto.trigger_prompt_snippet,
        tool_traces=[_to_harness_trace(t) for t in dto.tool_traces],
        counterexample_snippet=dto.counterexample_snippet,
        confidence_score=dto.confidence_score,
    )


def _to_dto_link(harness: ExtractionProvenanceLink) -> ExtractionProvenanceLinkDTO:
    """Convert harness ExtractionProvenanceLink to API ExtractionProvenanceLinkDTO."""
    return ExtractionProvenanceLinkDTO(
        link_id=harness.link_id,
        conversation_id=harness.conversation_id,
        turn_index=harness.turn_index,
        trigger_prompt_snippet=harness.trigger_prompt_snippet,
        tool_traces=[_to_dto_trace(t) for t in harness.tool_traces],
        counterexample_snippet=harness.counterexample_snippet,
        confidence_score=harness.confidence_score,
    )


def _to_harness_batch_item(dto: BatchLearnItemDTO) -> BatchLearnItem:
    """Convert API BatchLearnItemDTO to harness BatchLearnItem."""
    link = _to_harness_link(dto.provenance_link) if dto.provenance_link else None
    return BatchLearnItem(
        raw_id=dto.raw_id,
        content=dto.content,
        namespace=dto.namespace,
        scope_level=dto.scope_level,
        provenance_link=link,
    )


class MemoryProvenanceBatchService:
    """Service providing provenance link management and batch learning namespace isolation."""

    def __init__(
        self,
        linker: SkillProvenanceLinker | None = None,
        isolator: BatchLearnNamespaceIsolator | None = None,
    ) -> None:
        self._linker = linker or SkillProvenanceLinker()
        self._isolator = isolator or BatchLearnNamespaceIsolator()

    def create_provenance_link(
        self, request: CreateProvenanceLinkRequestDTO
    ) -> ExtractionProvenanceLinkDTO:
        """Create and validate an immutable provenance link from raw conversation and tool evidence."""
        harness_traces = [_to_harness_trace(t) for t in request.tool_traces]
        link = self._linker.create_provenance_link(
            conversation_id=request.conversation_id,
            trigger_prompt=request.trigger_prompt,
            turn_index=request.turn_index,
            tool_traces=harness_traces,
            counterexample=request.counterexample,
            confidence_score=request.confidence_score,
        )
        return _to_dto_link(link)

    def isolate_batch_learning(
        self, request: BatchLearnRequestDTO
    ) -> BatchLearnResponseDTO:
        """Process batch learning submissions, injecting deterministic namespaced identifiers."""
        harness_items = [_to_harness_batch_item(item) for item in request.items]
        result = self._isolator.isolate_batch(harness_items)

        namespaced_dtos = [
            NamespacedMemoryRefDTO(
                namespaced_id=ref.namespaced_id,
                namespace=ref.namespace,
                scope_level=ref.scope_level,
                raw_id=ref.raw_id,
            )
            for ref in result.namespaced_items
        ]

        return BatchLearnResponseDTO(
            total_items=result.total_items,
            namespaced_items=namespaced_dtos,
            has_provenance_count=result.has_provenance_count,
        )


_DEFAULT_SERVICE: MemoryProvenanceBatchService | None = None


def get_memory_provenance_batch_service() -> MemoryProvenanceBatchService:
    """Return default singleton MemoryProvenanceBatchService."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = MemoryProvenanceBatchService()
    return _DEFAULT_SERVICE
