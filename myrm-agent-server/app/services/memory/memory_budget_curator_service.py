"""
[POS] app/services/memory/memory_budget_curator_service.py
[INPUT] app.schemas.memory_budget_curator, myrm_agent_harness.toolkits.memory.budget_curator
[OUTPUT] MemoryBudgetCuratorService, get_memory_budget_curator_service

Service coordinating the Memory Budget Meter, Atomic Operations Curator, and Session Scroll Navigator.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.budget_curator import (
    AtomicBatchResult,
    AtomicOperationsCurator,
    ManagedMemoryItem,
    MemoryBatchOperation,
    MemoryBudgetMeter,
    MemoryBudgetSpec,
    MemoryBudgetStatus,
    MemoryOperationType,
    ScrollAnchorRequest,
    ScrollAnchorResult,
    ScrollMessageItem,
    SessionScrollNavigator,
)

from app.schemas.memory_budget_curator import (
    AtomicBatchRequestDTO,
    AtomicBatchResponseDTO,
    ManagedMemoryItemDTO,
    MemoryBatchOperationDTO,
    MemoryBudgetSpecDTO,
    MemoryBudgetStatusDTO,
    ScrollAnchorRequestDTO,
    ScrollAnchorResponseDTO,
    ScrollMessageItemDTO,
)


def _to_harness_item(dto: ManagedMemoryItemDTO) -> ManagedMemoryItem:
    """Convert ManagedMemoryItemDTO to harness ManagedMemoryItem."""
    return ManagedMemoryItem(
        item_id=dto.item_id,
        content=dto.content,
        token_count=dto.token_count,
    )


def _to_dto_item(harness: ManagedMemoryItem) -> ManagedMemoryItemDTO:
    """Convert harness ManagedMemoryItem to ManagedMemoryItemDTO."""
    return ManagedMemoryItemDTO(
        item_id=harness.item_id,
        content=harness.content,
        token_count=harness.token_count,
    )


def _to_harness_spec(dto: MemoryBudgetSpecDTO | None) -> MemoryBudgetSpec:
    """Convert MemoryBudgetSpecDTO to harness MemoryBudgetSpec."""
    if dto is None:
        return MemoryBudgetSpec()
    return MemoryBudgetSpec(
        max_tokens=dto.max_tokens,
        max_slots=dto.max_slots,
        warning_threshold_pct=dto.warning_threshold_pct,
    )


def _to_dto_status(harness: MemoryBudgetStatus) -> MemoryBudgetStatusDTO:
    """Convert harness MemoryBudgetStatus to MemoryBudgetStatusDTO."""
    return MemoryBudgetStatusDTO(
        used_tokens=harness.used_tokens,
        max_tokens=harness.max_tokens,
        token_usage_pct=harness.token_usage_pct,
        used_slots=harness.used_slots,
        max_slots=harness.max_slots,
        slot_usage_pct=harness.slot_usage_pct,
        is_warning=harness.is_warning,
        is_overflow=harness.is_overflow,
        budget_header_slice=harness.budget_header_slice,
    )


def _to_harness_op(dto: MemoryBatchOperationDTO) -> MemoryBatchOperation:
    """Convert MemoryBatchOperationDTO to harness MemoryBatchOperation."""
    op_type = MemoryOperationType.ADD
    try:
        op_type = MemoryOperationType(dto.operation_type.lower())
    except ValueError:
        pass

    return MemoryBatchOperation(
        operation_type=op_type,
        target_id=dto.target_id,
        target_substring=dto.target_substring,
        new_id=dto.new_id,
        new_content=dto.new_content,
        estimated_tokens=dto.estimated_tokens,
    )


def _to_dto_batch_result(result: AtomicBatchResult) -> AtomicBatchResponseDTO:
    """Convert harness AtomicBatchResult to AtomicBatchResponseDTO."""
    return AtomicBatchResponseDTO(
        is_success=result.is_success,
        applied_count=result.applied_count,
        rolled_back=result.rolled_back,
        error_message=result.error_message,
        current_budget=_to_dto_status(result.current_budget),
        retained_items=[_to_dto_item(it) for it in result.retained_items],
    )


def _to_harness_msg(dto: ScrollMessageItemDTO) -> ScrollMessageItem:
    """Convert ScrollMessageItemDTO to harness ScrollMessageItem."""
    return ScrollMessageItem(
        message_id=dto.message_id,
        role=dto.role,
        content=dto.content,
        created_at=dto.created_at,
    )


def _to_dto_scroll_result(result: ScrollAnchorResult) -> ScrollAnchorResponseDTO:
    """Convert harness ScrollAnchorResult to ScrollAnchorResponseDTO."""
    return ScrollAnchorResponseDTO(
        conversation_id=result.conversation_id,
        around_message_id=result.around_message_id,
        messages=[
            ScrollMessageItemDTO(
                message_id=m.message_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in result.messages
        ],
        has_more_before=result.has_more_before,
        has_more_after=result.has_more_after,
    )


class MemoryBudgetCuratorService:
    """Service providing memory budget evaluation, atomic curation, and sliding navigation."""

    def __init__(self, default_spec: MemoryBudgetSpec | None = None) -> None:
        self._spec = default_spec or MemoryBudgetSpec()
        self._meter = MemoryBudgetMeter(spec=self._spec)
        self._curator = AtomicOperationsCurator(meter=self._meter)
        self._navigator = SessionScrollNavigator()

    def evaluate_budget(
        self,
        items: list[ManagedMemoryItemDTO],
        spec_dto: MemoryBudgetSpecDTO | None = None,
    ) -> MemoryBudgetStatusDTO:
        """Evaluate and format the memory budget dashboard header."""
        spec = _to_harness_spec(spec_dto) if spec_dto else self._spec
        meter = MemoryBudgetMeter(spec=spec)
        harness_items = [_to_harness_item(it) for it in items]
        status = meter.evaluate_budget(harness_items)
        return _to_dto_status(status)

    def apply_atomic_batch(self, request: AtomicBatchRequestDTO) -> AtomicBatchResponseDTO:
        """Atomically execute a batch of memory curation operations."""
        spec = _to_harness_spec(request.budget_spec) if request.budget_spec else self._spec
        meter = MemoryBudgetMeter(spec=spec)
        curator = AtomicOperationsCurator(meter=meter)

        current_harness = [_to_harness_item(it) for it in request.current_items]
        ops_harness = [_to_harness_op(op) for op in request.operations]

        result = curator.apply_operations(current_harness, ops_harness)
        return _to_dto_batch_result(result)

    def scroll_around_message(
        self,
        messages: list[ScrollMessageItemDTO],
        request: ScrollAnchorRequestDTO,
    ) -> ScrollAnchorResponseDTO:
        """Traverse conversation history around a target anchor message ID."""
        harness_messages = [_to_harness_msg(m) for m in messages]
        harness_req = ScrollAnchorRequest(
            conversation_id=request.conversation_id,
            around_message_id=request.around_message_id,
            before_limit=request.before_limit,
            after_limit=request.after_limit,
        )
        result = self._navigator.scroll_around_message(harness_messages, harness_req)
        return _to_dto_scroll_result(result)


_budget_curator_service_instance: MemoryBudgetCuratorService | None = None


def get_memory_budget_curator_service() -> MemoryBudgetCuratorService:
    """Singleton getter for MemoryBudgetCuratorService."""
    global _budget_curator_service_instance
    if _budget_curator_service_instance is None:
        _budget_curator_service_instance = MemoryBudgetCuratorService()
    return _budget_curator_service_instance
