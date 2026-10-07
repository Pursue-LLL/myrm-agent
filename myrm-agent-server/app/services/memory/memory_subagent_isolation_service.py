"""
[POS] app/services/memory/memory_subagent_isolation_service.py
[INPUT] app.schemas.memory_subagent_isolation, myrm_agent_harness.agent.context_management.compression_flush
[OUTPUT] MemorySubagentIsolationService, get_memory_subagent_isolation_service

Service orchestrating Pre-Compression Memory Flush Hook, Subagent Memory Isolation, and Stateless Cron Context Guard.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.agent.context_management.compression_flush import (
    EphemeralMemoryOverlaySpec,
    FlushItem,
    FlushResult,
    FlushTriggerReason,
    MemoryIsolationScope,
    PreCompressionMemoryFlushHook,
    StatelessCronContextGuard,
    StatelessCronSpec,
    SubagentMemoryIsolationController,
    SubagentMemoryPolicy,
)

from app.schemas.memory_subagent_isolation import (
    CreateSubagentOverlayRequestDTO,
    FlushItemDTO,
    FlushResultDTO,
    StatelessCronSanitizeRequestDTO,
    StatelessCronSanitizeResponseDTO,
)


def _to_harness_item(dto: FlushItemDTO) -> FlushItem:
    """Convert FlushItemDTO to harness FlushItem."""
    return FlushItem(
        item_id=dto.item_id,
        category=dto.category,
        content=dto.content,
        source_turn=dto.source_turn,
        importance_score=dto.importance_score,
        tags=list(dto.tags),
        created_at=dto.created_at or "",
    )


def _to_dto_item(item: FlushItem) -> FlushItemDTO:
    """Convert harness FlushItem to FlushItemDTO."""
    return FlushItemDTO(
        item_id=item.item_id,
        category=item.category,
        content=item.content,
        source_turn=item.source_turn,
        importance_score=item.importance_score,
        tags=list(item.tags),
        created_at=item.created_at,
    )


def _to_dto_result(result: FlushResult) -> FlushResultDTO:
    """Convert harness FlushResult to FlushResultDTO."""
    return FlushResultDTO(
        session_id=result.session_id,
        reason=result.reason.value,
        is_success=result.is_success,
        flushed_items_count=result.flushed_items_count,
        flushed_categories=list(result.flushed_categories),
        timestamp=result.timestamp,
        error_message=result.error_message,
    )


class MemorySubagentIsolationService:
    """Service providing pre-compression flush coordination, subagent memory sandboxing, and cron isolation."""

    def __init__(self) -> None:
        self._flush_hook = PreCompressionMemoryFlushHook()
        self._isolation_controller = SubagentMemoryIsolationController()

    def register_pending_items(
        self, session_id: str, items: list[FlushItemDTO]
    ) -> int:
        """Register items into transient pending buffer awaiting pre-compression flush."""
        harness_items = [_to_harness_item(it) for it in items]
        self._flush_hook.register_pending_items(session_id, harness_items)
        return self._flush_hook.get_pending_count(session_id)

    def get_pending_count(self, session_id: str) -> int:
        """Retrieve total count of pending items for a session."""
        return self._flush_hook.get_pending_count(session_id)

    def execute_pre_compression_flush(
        self, session_id: str, reason_str: str = "compression"
    ) -> FlushResultDTO:
        """Execute pre-compression memory flush gate before summarizing or pruning context."""
        try:
            reason = FlushTriggerReason(reason_str.lower())
        except ValueError:
            reason = FlushTriggerReason.COMPRESSION

        result = self._flush_hook.execute_pre_compression_flush(session_id, reason)
        return _to_dto_result(result)

    def create_subagent_overlay(
        self, request: CreateSubagentOverlayRequestDTO
    ) -> bool:
        """Instantiate an ephemeral memory overlay for a derived subagent."""
        spec = EphemeralMemoryOverlaySpec(
            overlay_id=request.spec.overlay_id,
            parent_session_id=request.spec.parent_session_id,
            allow_selective_merge=request.spec.allow_selective_merge,
            auto_purge_on_finish=request.spec.auto_purge_on_finish,
            max_overlay_items=request.spec.max_overlay_items,
        )

        policy = None
        if request.policy is not None:
            try:
                scope = MemoryIsolationScope(request.policy.isolation_scope.lower())
            except ValueError:
                scope = MemoryIsolationScope.SUBAGENT_OVERLAY

            policy = SubagentMemoryPolicy(
                isolation_scope=scope,
                allow_profile_read=request.policy.allow_profile_read,
                allow_ephemeral_write=request.policy.allow_ephemeral_write,
                auto_purge=request.policy.auto_purge,
            )

        parent_items = [_to_harness_item(it) for it in request.parent_items]
        self._isolation_controller.create_subagent_overlay(
            spec, parent_items=parent_items, policy=policy
        )
        return self._isolation_controller.has_overlay(request.spec.overlay_id)

    def append_subagent_ephemeral(
        self, overlay_id: str, item: FlushItemDTO
    ) -> bool:
        """Append a scratch exploration item to subagent's private overlay."""
        harness_item = _to_harness_item(item)
        return self._isolation_controller.append_subagent_ephemeral(
            overlay_id, harness_item
        )

    def get_subagent_view(self, overlay_id: str) -> list[FlushItemDTO]:
        """Retrieve composite memory view for subagent."""
        items = self._isolation_controller.get_subagent_view(overlay_id)
        return [_to_dto_item(it) for it in items]

    def merge_selective_to_parent(
        self, overlay_id: str, selected_item_ids: list[str]
    ) -> list[FlushItemDTO]:
        """Harvest chosen findings from subagent overlay back to parent session."""
        harvested = self._isolation_controller.merge_selective_to_parent(
            overlay_id, selected_item_ids
        )
        return [_to_dto_item(it) for it in harvested]

    def purge_subagent_overlay(self, overlay_id: str) -> None:
        """Manually purge a subagent memory overlay."""
        self._isolation_controller.purge_overlay(overlay_id)

    def sanitize_cron_task_prompt(
        self, request: StatelessCronSanitizeRequestDTO
    ) -> StatelessCronSanitizeResponseDTO:
        """Cleanse automated task prompt to guarantee stateless, unpolluted execution."""
        spec = StatelessCronSpec(
            task_id=request.task_id,
            task_name=request.task_name,
            strip_user_profile=request.strip_user_profile,
            require_self_contained=request.require_self_contained,
        )

        sanitized, was_modified = StatelessCronContextGuard.sanitize_cron_prompt(
            request.raw_prompt, spec
        )
        is_self_contained = StatelessCronContextGuard.validate_self_contained(sanitized)

        return StatelessCronSanitizeResponseDTO(
            task_id=request.task_id,
            sanitized_prompt=sanitized,
            was_modified=was_modified,
            is_self_contained=is_self_contained,
        )


_subagent_isolation_service_instance: MemorySubagentIsolationService | None = None


def get_memory_subagent_isolation_service() -> MemorySubagentIsolationService:
    """Singleton getter for MemorySubagentIsolationService."""
    global _subagent_isolation_service_instance
    if _subagent_isolation_service_instance is None:
        _subagent_isolation_service_instance = MemorySubagentIsolationService()
    return _subagent_isolation_service_instance
