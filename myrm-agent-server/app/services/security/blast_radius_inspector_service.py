"""Service layer for Agent Blast Radius Static Inspector and Guard Attribution Suite.

[POS] app/services/security/blast_radius_inspector_service.py
[INPUT] app/schemas/blast_radius_inspector.py, myrm_agent_harness.core.security.blast_radius_inspector
[OUTPUT] BlastRadiusInspectorService
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.core.security.blast_radius_inspector import (
    ActionSurfaceDimension,
    ActionSurfaceStaticInspector,
    AtomicActionCategory,
    DangerTier,
    GlobalActionKillSwitch,
    GuardAttributionEngine,
    GuardStatus,
    SinkVulnerabilityItem,
)

from app.schemas.blast_radius_inspector import (
    ActionSurfaceExposureReportDTO,
    ActionSurfaceInspectRequest,
    AutoRepairPatchRequest,
    AutoRepairPatchResponse,
    GuardAttributionItemDTO,
    GuardAttributionRequest,
    GuardAttributionResponse,
    KillSwitchStatusResponse,
    RepairPolicyPatchDTO,
    SinkVulnerabilityDTO,
    ToggleKillSwitchRequest,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


class BlastRadiusInspectorService:
    """Service coordinating static action surface discovery, guard attribution, and emergency kill switches."""

    def __init__(self) -> None:
        self._inspector = ActionSurfaceStaticInspector()
        self._attribution_engine = GuardAttributionEngine()
        self._kill_switch = GlobalActionKillSwitch()

    def inspect_action_surface(
        self, request: ActionSurfaceInspectRequest
    ) -> ActionSurfaceExposureReportDTO:
        """Statically inspect agent tools and configurations to compute exposure surfaces."""
        report, raw_sinks = self._inspector.inspect_profile(
            tools=request.tools,
            declared_file_scopes=request.declared_file_scopes,
            declared_api_endpoints=request.declared_api_endpoints,
            declared_send_channels=request.declared_send_channels,
            installed_plugins=request.installed_plugins,
        )

        sink_dtos: list[SinkVulnerabilityDTO] = [
            self._harness_sink_to_dto(s) for s in raw_sinks
        ]

        logger.info(
            "Action surface inspection complete for profile=%s: total_tools=%d, pre_admission_allowed=%s",
            request.profile_id,
            report.total_tools_count,
            report.pre_admission_allowed,
        )

        return ActionSurfaceExposureReportDTO(
            profile_id=request.profile_id,
            total_tools_count=report.total_tools_count,
            total_files_scope_count=report.total_files_scope_count,
            total_apis_count=report.total_apis_count,
            total_sends_count=report.total_sends_count,
            action_breakdown=report.action_breakdown,
            reachable_verified_count=report.reachable_verified_count,
            install_liability_count=report.install_liability_count,
            unguarded_critical_count=report.unguarded_critical_count,
            exposure_score=report.exposure_score,
            pre_admission_allowed=report.pre_admission_allowed,
            admission_rejection_reason=report.admission_rejection_reason,
            sinks=sink_dtos,
        )

    def attribute_guards(
        self, request: GuardAttributionRequest
    ) -> GuardAttributionResponse:
        """Map active runtime guards to identified sinks and assess protection status."""
        converted_sinks = [
            self._dto_to_harness_sink(s) for s in request.sinks
        ]

        attribution_items = self._attribution_engine.attribute_guards(
            sinks=converted_sinks,
            active_guards=request.active_guards,
        )

        item_dtos: list[GuardAttributionItemDTO] = []
        attributed_count = 0
        unguarded_count = 0

        for attr in attribution_items:
            if attr.guard_status == GuardStatus.GUARD_ATTRIBUTED:
                attributed_count += 1
            else:
                unguarded_count += 1

            item_dtos.append(
                GuardAttributionItemDTO(
                    sink=self._harness_sink_to_dto(attr.sink),
                    guard_status=attr.guard_status.value,
                    assigned_guard_name=attr.assigned_guard_name,
                    recommended_policy_fix=attr.recommended_policy_fix,
                )
            )

        return GuardAttributionResponse(
            attributions=item_dtos,
            attributed_count=attributed_count,
            unguarded_count=unguarded_count,
            remediation_required=unguarded_count > 0,
        )

    def synthesize_auto_repairs(
        self, request: AutoRepairPatchRequest
    ) -> AutoRepairPatchResponse:
        """Synthesize automatic least-privilege repair patches for unguarded sinks."""
        converted_sinks = [
            self._dto_to_harness_sink(s) for s in request.sinks
        ]

        attributed_items = self._attribution_engine.attribute_guards(
            sinks=converted_sinks,
            active_guards=request.active_guards,
        )

        patches = self._attribution_engine.synthesize_repair_patches(
            attributed_items=attributed_items
        )

        patch_dtos: list[RepairPolicyPatchDTO] = [
            RepairPolicyPatchDTO(
                patch_id=p.patch_id,
                target_sink=p.target_sink,
                injected_guard_type=p.injected_guard_type,
                patch_configuration=p.patch_configuration,
                rationale=p.rationale,
            )
            for p in patches
        ]

        return AutoRepairPatchResponse(
            patches=patch_dtos,
            total_patches=len(patch_dtos),
        )

    def toggle_kill_switch(
        self, request: ToggleKillSwitchRequest
    ) -> KillSwitchStatusResponse:
        """Engage or disengage the global action kill switch."""
        if request.enabled:
            state = self._kill_switch.engage(
                operator_identity=request.operator,
                reason=request.reason,
            )
        else:
            state = self._kill_switch.disengage()

        return KillSwitchStatusResponse(
            is_engaged=state.is_engaged,
            engaged_by=state.engaged_by,
            reason=state.reason,
            engaged_at=state.engaged_at,
        )

    def get_kill_switch_status(self) -> KillSwitchStatusResponse:
        """Fetch current operational status of the global kill switch."""
        state = self._kill_switch.get_state()
        return KillSwitchStatusResponse(
            is_engaged=state.is_engaged,
            engaged_by=state.engaged_by,
            reason=state.reason,
            engaged_at=state.engaged_at,
        )

    @staticmethod
    def _dto_to_harness_sink(dto: SinkVulnerabilityDTO) -> SinkVulnerabilityItem:
        """Convert a REST SinkVulnerabilityDTO to a typed Harness SinkVulnerabilityItem."""
        return SinkVulnerabilityItem(
            action_category=AtomicActionCategory(dto.action_category),
            dimension=ActionSurfaceDimension(dto.dimension),
            sink_identifier=dto.sink_identifier,
            danger_tier=DangerTier(dto.danger_tier),
            description=dto.description,
        )

    @staticmethod
    def _harness_sink_to_dto(sink: SinkVulnerabilityItem) -> SinkVulnerabilityDTO:
        """Convert a Harness SinkVulnerabilityItem to a REST SinkVulnerabilityDTO."""
        return SinkVulnerabilityDTO(
            action_category=sink.action_category.value,
            dimension=sink.dimension.value,
            sink_identifier=sink.sink_identifier,
            danger_tier=sink.danger_tier.value,
            description=sink.description,
        )


_service_instance: BlastRadiusInspectorService | None = None


def get_blast_radius_service() -> BlastRadiusInspectorService:
    """Return the global BlastRadiusInspectorService singleton instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = BlastRadiusInspectorService()
    return _service_instance
