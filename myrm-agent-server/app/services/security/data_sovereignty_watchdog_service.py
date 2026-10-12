"""
[POS] app/services/security/data_sovereignty_watchdog_service.py
[INPUT] myrm_agent_harness.core.security.data_sovereignty_watchdog, app.schemas.data_sovereignty_watchdog
[OUTPUT] DataSovereigntyWatchdogService, get_data_sovereignty_watchdog_service

Domain service mediating requests for Private Sandbox Data Sovereignty & Sub-Intrusive Watchdog.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.data_sovereignty_watchdog import (
    DataSovereigntyWatchdogSuite,
    HighStakesActionType,
    HighStakesConsentTicket,
    SovereigntySealLevel,
    SovereigntySealManifest,
    SubIntrusiveNotificationCard,
)

from app.schemas.data_sovereignty_watchdog import (
    ConsentDecisionRequest,
    CreateConsentTicketRequest,
    DataSovereigntyWatchdogMetricsResponse,
    EvaluateSuggestionRequest,
    HighStakesActionTypeResponse,
    HighStakesConsentTicketResponse,
    IssueSovereigntySealRequest,
    ProactivityValueLevelResponse,
    SovereigntySealLevelResponse,
    SovereigntySealManifestResponse,
    SubIntrusiveNotificationCardResponse,
    VerifySovereigntySealRequest,
    VerifySovereigntySealResponse,
)


class DataSovereigntyWatchdogService:
    """Service orchestrating private sandbox sovereignty seals, sub-intrusive card gating, and consent tickets."""

    def __init__(self, suite: DataSovereigntyWatchdogSuite | None = None) -> None:
        self._suite = suite or DataSovereigntyWatchdogSuite()

    def issue_sovereignty_seal(
        self, req: IssueSovereigntySealRequest
    ) -> SovereigntySealManifestResponse:
        """Issue an immutable data sovereignty seal confirming private volume isolation."""
        level = SovereigntySealLevel(req.seal_level.value)
        manifest = self._suite.issue_sovereignty_seal(
            storage_target=req.storage_target,
            volume_mount_path=req.volume_mount_path,
            seal_level=level,
        )
        return self._to_seal_response(manifest)

    def verify_sovereignty_seal(
        self, req: VerifySovereigntySealRequest
    ) -> VerifySovereigntySealResponse:
        """Verify cryptographic integrity of an issued sovereignty seal."""
        is_valid = self._suite.verify_sovereignty_seal(req.seal_id)
        return VerifySovereigntySealResponse(seal_id=req.seal_id, is_valid=is_valid)

    def get_latest_seal(self) -> SovereigntySealManifestResponse | None:
        """Retrieve most recently issued sovereignty seal."""
        manifest = self._suite.get_latest_seal()
        return self._to_seal_response(manifest) if manifest else None

    def evaluate_proactive_suggestion(
        self, req: EvaluateSuggestionRequest
    ) -> SubIntrusiveNotificationCardResponse:
        """Evaluate background inspection finding against anti-annoyance value thresholds."""
        card = self._suite.evaluate_proactive_suggestion(
            title=req.title,
            service_name=req.service_name,
            potential_savings_cents=req.potential_savings_cents,
            deadline_epoch=req.deadline_epoch,
            message=req.message,
        )
        return self._to_card_response(card)

    def list_active_notification_cards(self) -> list[SubIntrusiveNotificationCardResponse]:
        """List high-value alert cards that were not suppressed."""
        cards = self._suite.list_active_notification_cards()
        return [self._to_card_response(c) for c in cards]

    def list_all_notification_cards(self) -> list[SubIntrusiveNotificationCardResponse]:
        """List all evaluated cards including suppressed noise."""
        cards = self._suite.list_all_notification_cards()
        return [self._to_card_response(c) for c in cards]

    def create_high_stakes_consent(
        self, req: CreateConsentTicketRequest
    ) -> HighStakesConsentTicketResponse:
        """Lock high-stakes operation behind a pending consent ticket requiring explicit human authorization."""
        action_type = HighStakesActionType(req.action_type.value)
        ticket = self._suite.create_high_stakes_consent(
            action_type=action_type,
            service_name=req.service_name,
            financial_impact_cents=req.financial_impact_cents,
            payload_summary=req.payload_summary,
        )
        return self._to_ticket_response(ticket)

    def approve_consent(self, req: ConsentDecisionRequest) -> HighStakesConsentTicketResponse:
        """Operator authorizes a pending high-stakes financial mutation ticket."""
        ticket = self._suite.approve_consent(req.ticket_id)
        return self._to_ticket_response(ticket)

    def deny_consent(self, req: ConsentDecisionRequest) -> HighStakesConsentTicketResponse:
        """Operator explicitly denies a pending high-stakes financial mutation ticket."""
        ticket = self._suite.deny_consent(req.ticket_id)
        return self._to_ticket_response(ticket)

    def list_pending_consents(self) -> list[HighStakesConsentTicketResponse]:
        """List all operations currently awaiting human consent."""
        tickets = self._suite.list_pending_consents()
        return [self._to_ticket_response(t) for t in tickets]

    def get_metrics(self) -> DataSovereigntyWatchdogMetricsResponse:
        """Fetch cumulative operational metrics."""
        m = self._suite.metrics
        return DataSovereigntyWatchdogMetricsResponse(
            sovereignty_seals_issued_total=m.sovereignty_seals_issued_total,
            proactive_scans_total=m.proactive_scans_total,
            noise_suppressed_total=m.noise_suppressed_total,
            high_value_alerts_emitted_total=m.high_value_alerts_emitted_total,
            high_stakes_actions_blocked_total=m.high_stakes_actions_blocked_total,
            high_stakes_consents_approved_total=m.high_stakes_consents_approved_total,
            high_stakes_consents_denied_total=m.high_stakes_consents_denied_total,
        )

    @staticmethod
    def _to_seal_response(manifest: SovereigntySealManifest) -> SovereigntySealManifestResponse:
        return SovereigntySealManifestResponse(
            seal_id=manifest.seal_id,
            storage_target=manifest.storage_target,
            seal_level=SovereigntySealLevelResponse(manifest.seal_level.value),
            central_cloud_zero_retention=manifest.central_cloud_zero_retention,
            volume_mount_path=manifest.volume_mount_path,
            created_at=manifest.created_at,
            checksum=manifest.checksum,
        )

    @staticmethod
    def _to_card_response(card: SubIntrusiveNotificationCard) -> SubIntrusiveNotificationCardResponse:
        return SubIntrusiveNotificationCardResponse(
            card_id=card.card_id,
            title=card.title,
            potential_savings_cents=card.potential_savings_cents,
            deadline_epoch=card.deadline_epoch,
            value_level=ProactivityValueLevelResponse(card.value_level.value),
            is_suppressed=card.is_suppressed,
            message=card.message,
            service_name=card.service_name,
        )

    @staticmethod
    def _to_ticket_response(ticket: HighStakesConsentTicket) -> HighStakesConsentTicketResponse:
        return HighStakesConsentTicketResponse(
            ticket_id=ticket.ticket_id,
            action_type=HighStakesActionTypeResponse(ticket.action_type.value),
            service_name=ticket.service_name,
            financial_impact_cents=ticket.financial_impact_cents,
            payload_summary=ticket.payload_summary,
            is_approved=ticket.is_approved,
            is_denied=ticket.is_denied,
            created_at=ticket.created_at,
        )


_default_service: DataSovereigntyWatchdogService | None = None


def get_data_sovereignty_watchdog_service() -> DataSovereigntyWatchdogService:
    """Dependency injection provider for DataSovereigntyWatchdogService."""
    global _default_service
    if _default_service is None:
        _default_service = DataSovereigntyWatchdogService()
    return _default_service
