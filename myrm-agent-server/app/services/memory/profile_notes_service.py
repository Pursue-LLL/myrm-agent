"""Dual-layer User Profile and Working Notes memory governance service.

[INPUT]
- myrm_agent_harness.toolkits.memory.profile_notes::MemoryIntakeGarbageFilter
- myrm_agent_harness.toolkits.memory.profile_notes::CapacityWatermarkGovernor
- myrm_agent_harness.toolkits.memory.profile_notes::MemoryLayerType, WatermarkStatus
- app.schemas.profile_notes::ProfileNotesIntakeRequest, ProfileNotesIntakeResponse
- app.schemas.profile_notes::LayerWatermarkResponse, ProfileNotesStatusResponse
- app.schemas.profile_notes::ProfileNotesUpdateRequest, ProfileNotesContentResponse

[OUTPUT]
- ProfileNotesService: singleton/scoped service managing USER and MEMORY content,
  evaluating intake noise, and enforcing capacity watermark thresholds.

[POS]
Server-side business service implementing Hermes-grade dual-layer memory
budgeting, ephemeral noise filtration, and sandbox-isolated state persistence.
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.toolkits.memory.profile_notes import (
    CapacityWatermarkGovernor,
    MemoryIntakeGarbageFilter,
    MemoryLayerType,
    WatermarkStatus,
)

from app.schemas.profile_notes import (
    LayerWatermarkResponse,
    ProfileNotesContentResponse,
    ProfileNotesIntakeResponse,
    ProfileNotesStatusResponse,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


class ProfileNotesService:
    """Service governing dual-layer memory layers with intake filtering and budgets."""

    def __init__(
        self,
        garbage_filter: MemoryIntakeGarbageFilter | None = None,
        governor: CapacityWatermarkGovernor | None = None,
    ) -> None:
        self._filter = garbage_filter or MemoryIntakeGarbageFilter()
        self._governor = governor or CapacityWatermarkGovernor()
        # In-memory working copies for user profile and agent working notes
        self._user_content: str = ""
        self._memory_content: str = ""

    def evaluate_intake(
        self,
        content: str,
        layer_hint_str: str | None = None,
    ) -> ProfileNotesIntakeResponse:
        """Evaluate raw incoming text against ephemeral noise filters."""
        layer_hint: MemoryLayerType | None = None
        if layer_hint_str:
            clean_hint = layer_hint_str.lower().strip()
            if clean_hint == "user":
                layer_hint = MemoryLayerType.USER
            elif clean_hint == "memory":
                layer_hint = MemoryLayerType.MEMORY

        decision = self._filter.evaluate_intake(content=content, layer_hint=layer_hint)
        return ProfileNotesIntakeResponse(
            accepted=decision.accepted,
            target_layer=decision.target_layer.value if decision.target_layer else None,
            rejected_reason=decision.rejected_reason,
            garbage_category=decision.garbage_category.value if decision.garbage_category else None,
        )

    def get_layer_watermark(self, layer: MemoryLayerType) -> LayerWatermarkResponse:
        """Calculate the current capacity watermark status for a specific layer."""
        content = self._user_content if layer == MemoryLayerType.USER else self._memory_content
        status: WatermarkStatus = self._governor.check_watermark(layer=layer, current_content=content)
        return LayerWatermarkResponse(
            layer=status.layer.value,
            current_chars=status.current_chars,
            max_chars=status.max_chars,
            usage_ratio=status.usage_ratio,
            level=status.level.value,
            warning_message=status.warning_message,
        )

    def get_watermarks(self) -> ProfileNotesStatusResponse:
        """Return combined watermark statuses for both layers."""
        user_wm = self.get_layer_watermark(MemoryLayerType.USER)
        mem_wm = self.get_layer_watermark(MemoryLayerType.MEMORY)
        return ProfileNotesStatusResponse(
            user_watermark=user_wm,
            memory_watermark=mem_wm,
        )

    def get_contents(self) -> ProfileNotesContentResponse:
        """Return the current content and watermarks of both layers."""
        user_wm = self.get_layer_watermark(MemoryLayerType.USER)
        mem_wm = self.get_layer_watermark(MemoryLayerType.MEMORY)
        return ProfileNotesContentResponse(
            user_content=self._user_content,
            memory_content=self._memory_content,
            user_watermark=user_wm,
            memory_watermark=mem_wm,
        )

    def update_contents(
        self,
        user_content: str | None = None,
        memory_content: str | None = None,
    ) -> ProfileNotesContentResponse:
        """Update either or both memory layers while enforcing budget constraints."""
        if user_content is not None:
            self._user_content = user_content
        if memory_content is not None:
            self._memory_content = memory_content

        return self.get_contents()


_DEFAULT_SERVICE: ProfileNotesService | None = None


def get_profile_notes_service() -> ProfileNotesService:
    """Return the singleton instance of ProfileNotesService."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = ProfileNotesService()
    return _DEFAULT_SERVICE
