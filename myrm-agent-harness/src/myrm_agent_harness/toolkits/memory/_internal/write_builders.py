"""Constructors of the memories the convenience writes persist.

[INPUT]
- memory._internal.scope::{MemoryWriteTarget, scope_for_write_target} (POS: write scope selection)
- memory.types::{EpisodicMemory, MemoryScope, ProceduralMemory, RuleSource, SemanticMemory} (POS: memory data models)

[OUTPUT]
- MemoryBuildersMixin: build_knowledge, build_event, build_pitfall, build_rule

[POS]
The memory objects behind ``add_knowledge``, ``add_event``, ``add_pitfall`` and ``add_rule``, bound to the writer's scope
and carrying the chat the caller wrote them from. Mixed into the writer, which persists what they build.
Not part of the public API.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory._internal.scope import (
    MemoryWriteTarget,
    scope_for_write_target,
)
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemoryScope,
    ProceduralMemory,
    RuleSource,
    SemanticMemory,
)


class MemoryBuildersMixin:
    """Builds the memories of the convenience writes in the writer's scope."""

    __slots__ = ()

    _scope: MemoryScope
    _namespaces: list[str]

    def build_knowledge(
        self,
        content: str,
        *,
        importance: float = 0.5,
        tags: list[str] | None = None,
        source_chat_id: str | None = None,
        write_target: MemoryWriteTarget = "bound",
    ) -> SemanticMemory:
        return SemanticMemory(
            content=content,
            importance=importance,
            tags=tags or [],
            source_chat_id=source_chat_id,
            scope=scope_for_write_target(self._scope, self._namespaces, write_target),
        )

    def build_event(
        self,
        content: str,
        *,
        event_type: str = "conversation",
        related_entities: list[str] | None = None,
        source_chat_id: str | None = None,
        source_message_id: str | None = None,
        subtask_phase: Literal["analyze", "locate", "edit", "verify"] | None = None,
        is_failure_attempt: bool = False,
        failure_reason: str | None = None,
        negative_lesson: str | None = None,
        confidence_tier: Literal["strong", "weak", "shadow"] = "strong",
        write_target: MemoryWriteTarget = "bound",
    ) -> EpisodicMemory:
        return EpisodicMemory(
            content=content,
            event_type=event_type,
            related_entities=related_entities or [],
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            subtask_phase=subtask_phase,
            is_failure_attempt=is_failure_attempt,
            failure_reason=failure_reason,
            negative_lesson=negative_lesson,
            confidence_tier=confidence_tier,
            scope=scope_for_write_target(self._scope, self._namespaces, write_target),
        )

    def build_pitfall(
        self,
        content: str,
        *,
        failure_reason: str,
        negative_lesson: str,
        subtask_phase: Literal["analyze", "locate", "edit", "verify"] | None = None,
        confidence_tier: Literal["strong", "weak", "shadow"] = "strong",
        related_entities: list[str] | None = None,
        source_chat_id: str | None = None,
        source_message_id: str | None = None,
        write_target: MemoryWriteTarget = "bound",
    ) -> EpisodicMemory:
        cleaned_reason = failure_reason.strip() if failure_reason else ""
        cleaned_lesson = negative_lesson.strip() if negative_lesson else ""
        fallback_lesson = cleaned_lesson or cleaned_reason or content.strip()

        return EpisodicMemory(
            content=content,
            event_type="failed_attempt",
            related_entities=related_entities or [],
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            subtask_phase=subtask_phase,
            is_failure_attempt=True,
            failure_reason=cleaned_reason or "Unspecified failure cause",
            negative_lesson=fallback_lesson,
            confidence_tier=confidence_tier,
            scope=scope_for_write_target(self._scope, self._namespaces, write_target),
        )

    def build_rule(
        self,
        trigger: str,
        action: str,
        *,
        priority: int = 0,
        trigger_keywords: list[str] | None = None,
        source: RuleSource = RuleSource.USER_EXTRACTED,
        source_chat_id: str | None = None,
    ) -> ProceduralMemory:
        return ProceduralMemory(
            content=f"When: {trigger} → Do: {action}",
            trigger=trigger,
            action=action,
            priority=priority,
            trigger_keywords=trigger_keywords or [],
            source=source,
            source_chat_id=source_chat_id,
            scope=self._scope.model_copy(deep=True),
        )
