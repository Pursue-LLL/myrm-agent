"""
[POS] app/services/security/live_session_credential_shield_service.py
[INPUT] myrm_agent_harness.core.security.live_session_credential_shield, app.schemas.live_session_credential_shield
[OUTPUT] LiveSessionCredentialShieldService, get_live_session_credential_shield_service

Domain service mediating requests for Live Session Out-of-Band Credential Input Shield.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.live_session_credential_shield import (
    BlindCredentialInputEvent,
    BoundingBox,
    DOMRedactionRule,
    LiveSessionCredentialShieldSuite,
    MaskingRedactionReport,
    ScreenMaskRegion,
    SensitiveTargetType,
)

from app.schemas.live_session_credential_shield import (
    AirlockChannelStatusResponse,
    AirlockStatusResponse,
    BlindCredentialInputEventResponse,
    BoundingBoxSchema,
    CloseAirlockRequest,
    HandoverScrubRequest,
    HandoverScrubResponse,
    LiveSessionShieldMetricsResponse,
    MaskingRedactionReportResponse,
    OpenAirlockRequest,
    RedactDOMRequest,
    RedactDOMResponse,
    RegisterMaskRegionRequest,
    RouteBlindInputRequest,
    RouteBlindInputResponse,
    ScreenMaskRegionResponse,
    SensitiveTargetTypeResponse,
)


class LiveSessionCredentialShieldService:
    """Service orchestrating out-of-band credential airlocks and post-takeover screen/DOM masking."""

    def __init__(self, suite: LiveSessionCredentialShieldSuite | None = None) -> None:
        self._suite = suite or LiveSessionCredentialShieldSuite()

    def open_airlock(self, req: OpenAirlockRequest) -> AirlockStatusResponse:
        """Open an out-of-band input airlock for a live session."""
        status = self._suite.open_airlock(req.session_id)
        return AirlockStatusResponse(
            session_id=req.session_id,
            status=AirlockChannelStatusResponse(status.value),
        )

    def close_airlock(self, req: CloseAirlockRequest) -> AirlockStatusResponse:
        """Close an out-of-band input airlock channel."""
        status = self._suite.close_airlock(req.session_id)
        return AirlockStatusResponse(
            session_id=req.session_id,
            status=AirlockChannelStatusResponse(status.value),
        )

    def get_airlock_status(self, session_id: str) -> AirlockStatusResponse:
        """Query active status of an airlock channel."""
        status = self._suite.get_airlock_status(session_id)
        return AirlockStatusResponse(
            session_id=session_id,
            status=AirlockChannelStatusResponse(status.value),
        )

    def route_blind_input(self, req: RouteBlindInputRequest) -> RouteBlindInputResponse:
        """Route keystrokes via blind airlock channel, ensuring Agent observation is shielded."""
        target_type = (
            SensitiveTargetType(req.target_type.value) if req.target_type else None
        )
        event, dispatch_id = self._suite.route_blind_input(
            session_id=req.session_id,
            target_selector=req.target_selector,
            raw_secret=req.raw_secret,
            target_type=target_type,
        )
        return RouteBlindInputResponse(
            event=self._to_event_response(event),
            dispatch_confirmation_id=dispatch_id,
        )

    def register_mask_region(self, req: RegisterMaskRegionRequest) -> ScreenMaskRegionResponse:
        """Designate a screen coordinate bounding box for opaque pixel masking."""
        box = BoundingBox(
            x=req.box.x,
            y=req.box.y,
            width=req.box.width,
            height=req.box.height,
        )
        region = self._suite.register_mask_region(
            session_id=req.session_id,
            box=box,
            target_selector=req.target_selector,
            mask_color=req.mask_color,
        )
        return self._to_region_response(region)

    def list_mask_regions(self, session_id: str) -> list[ScreenMaskRegionResponse]:
        """Retrieve all active screen mask regions for a session."""
        regions = self._suite.list_mask_regions(session_id)
        return [self._to_region_response(r) for r in regions]

    def redact_dom_tree(self, req: RedactDOMRequest) -> RedactDOMResponse:
        """Scrub password inputs and secret tokens from DOM HTML before providing to LLM context."""
        rules = (
            tuple(
                DOMRedactionRule(
                    selector_pattern=r.selector_pattern,
                    attribute_to_redact=r.attribute_to_redact,
                    replacement_value=r.replacement_value,
                )
                for r in req.custom_rules
            )
            if req.custom_rules
            else None
        )
        sanitized_dom, count = self._suite.redact_dom_tree(
            dom_html=req.dom_html,
            custom_rules=rules,
        )
        return RedactDOMResponse(
            sanitized_dom=sanitized_dom,
            redacted_nodes_count=count,
        )

    def execute_handover_scrub(self, req: HandoverScrubRequest) -> HandoverScrubResponse:
        """Atomically execute screen-DOM redactions when handing control back to Agent."""
        sanitized_dom, report = self._suite.execute_handover_scrub(
            session_id=req.session_id,
            dom_html=req.dom_html,
        )
        return HandoverScrubResponse(
            sanitized_dom=sanitized_dom,
            report=self._to_report_response(report),
        )

    def list_session_blind_events(
        self, session_id: str
    ) -> list[BlindCredentialInputEventResponse]:
        """List historical blind input audit events."""
        events = self._suite.list_session_blind_events(session_id)
        return [self._to_event_response(e) for e in events]

    def get_metrics(self) -> LiveSessionShieldMetricsResponse:
        """Fetch cumulative operational metrics."""
        m = self._suite.metrics
        return LiveSessionShieldMetricsResponse(
            blind_inputs_routed_total=m.blind_inputs_routed_total,
            screen_masks_applied_total=m.screen_masks_applied_total,
            dom_nodes_redacted_total=m.dom_nodes_redacted_total,
            handover_scrubs_completed_total=m.handover_scrubs_completed_total,
            prompt_injections_mitigated_total=m.prompt_injections_mitigated_total,
        )

    @staticmethod
    def _to_event_response(event: BlindCredentialInputEvent) -> BlindCredentialInputEventResponse:
        return BlindCredentialInputEventResponse(
            session_id=event.session_id,
            target_selector=event.target_selector,
            target_type=SensitiveTargetTypeResponse(event.target_type.value),
            keystroke_count=event.keystroke_count,
            is_blind_routed=event.is_blind_routed,
            timestamp=event.timestamp,
        )

    @staticmethod
    def _to_region_response(region: ScreenMaskRegion) -> ScreenMaskRegionResponse:
        return ScreenMaskRegionResponse(
            region_id=region.region_id,
            box=BoundingBoxSchema(
                x=region.box.x,
                y=region.box.y,
                width=region.box.width,
                height=region.box.height,
            ),
            mask_color=region.mask_color,
            target_selector=region.target_selector,
        )

    @staticmethod
    def _to_report_response(report: MaskingRedactionReport) -> MaskingRedactionReportResponse:
        return MaskingRedactionReportResponse(
            session_id=report.session_id,
            masked_regions_count=report.masked_regions_count,
            redacted_dom_nodes_count=report.redacted_dom_nodes_count,
            observation_scrubbed=report.observation_scrubbed,
            timestamp=report.timestamp,
        )


_default_service: LiveSessionCredentialShieldService | None = None


def get_live_session_credential_shield_service() -> LiveSessionCredentialShieldService:
    """Dependency injection provider for LiveSessionCredentialShieldService."""
    global _default_service
    if _default_service is None:
        _default_service = LiveSessionCredentialShieldService()
    return _default_service
