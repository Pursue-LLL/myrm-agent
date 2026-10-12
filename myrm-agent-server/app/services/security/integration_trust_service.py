"""Integration Egress Trust Service.

[INPUT]
- myrm_agent_harness.core.security.integration_trust::IntegrationLifecycleEngine
  (POS: disclosure registry and provider revocation configs)

[OUTPUT]
- PreConnectDisclosureDto, ProviderRevokeConfigDto.

[POS]
- Server security service. Wraps the harness IntegrationLifecycleEngine registries to
  serve pre-connect disclosure cards and provider token revocation configs.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.integration_trust import (
    IntegrationLifecycleEngine,
    PreConnectDisclosure,
    ProviderRevokeConfig,
)

from app.schemas.integration_trust import (
    PreConnectDisclosureDto,
    ProviderRevokeConfigDto,
)


def _to_dto_disclosure(domain: PreConnectDisclosure) -> PreConnectDisclosureDto:
    return PreConnectDisclosureDto(
        provider_id=domain.provider_id,
        display_name=domain.display_name,
        data_types_read=list(domain.data_types_read),
        actions_performed=list(domain.actions_performed),
        storage_locations=list(domain.storage_locations),
        purge_policy_summary=domain.purge_policy_summary,
        flow_direction=domain.flow_direction.value,
    )


def _to_dto_revoke_config(domain: ProviderRevokeConfig) -> ProviderRevokeConfigDto:
    return ProviderRevokeConfigDto(
        provider_id=domain.provider_id,
        revocation_endpoint=domain.revocation_endpoint,
        supports_remote_revoke=domain.supports_remote_revoke,
        manual_revoke_url=domain.manual_revoke_url,
    )


class IntegrationTrustService:
    """Service exposing pre-connect transparency cards and provider revocation configs."""

    def __init__(self) -> None:
        self._engine = IntegrationLifecycleEngine()

    def get_disclosure(self, provider_id: str) -> PreConnectDisclosureDto | None:
        """Retrieve pre-connect disclosure card for an integration provider."""
        disc = self._engine.disclosure_registry.get_disclosure(provider_id)
        return _to_dto_disclosure(disc) if disc else None

    def list_disclosures(self) -> list[PreConnectDisclosureDto]:
        """List all registered pre-connect disclosures."""
        discs = self._engine.disclosure_registry.list_disclosures()
        return [_to_dto_disclosure(d) for d in discs]

    def get_revoke_config(self, provider_id: str) -> ProviderRevokeConfigDto | None:
        """Retrieve token revocation configuration for a provider."""
        cfg = self._engine.get_revoke_config(provider_id)
        return _to_dto_revoke_config(cfg) if cfg else None


_service_instance: IntegrationTrustService | None = None


def get_integration_trust_service() -> IntegrationTrustService:
    """Obtain or initialize singleton IntegrationTrustService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = IntegrationTrustService()
    return _service_instance
