"""Service layer coordinating domain isolation, bindings, and security guards.

[INPUT]
- Connector domain binding requests, grant updates, and cross-domain verification queries.

[OUTPUT]
- ConnectorDomainBindingDTO, DomainGrantConfigDTO, and EgressDecisionDTO.

[POS]
- Server-side business service for Item 156 ConnectionAndAccountDomainIsolation.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory.domain_isolation import (
    ConnectorDomainBinding,
    DomainGrantConfig,
    DomainIsolationGuard,
    DomainIsolationRegistry,
    EgressDecision,
)

from app.schemas.domain_isolation import (
    ConnectorDomainBindingDTO,
    DataDomainDTO,
    DomainGrantConfigDTO,
    EgressDecisionDTO,
    EvaluateEgressRequestDTO,
    SetConnectorDomainRequest,
    UpdateDomainGrantRequest,
    ValidateRecallRequestDTO,
    ValidateRecallResponseDTO,
    ValidateWriteRequestDTO,
    ValidateWriteResponseDTO,
)


class DomainIsolationService:
    """Business service orchestrating connector domains, granular grants, and privacy redlines."""

    def __init__(
        self,
        registry: DomainIsolationRegistry | None = None,
        guard: DomainIsolationGuard | None = None,
        storage_path: Path | str | None = None,
    ) -> None:
        self.registry = registry or DomainIsolationRegistry(storage_path=storage_path)
        self.guard = guard or DomainIsolationGuard(registry=self.registry)

    @staticmethod
    def _binding_to_dto(b: ConnectorDomainBinding) -> ConnectorDomainBindingDTO:
        return ConnectorDomainBindingDTO(
            connector_id=b.connector_id,
            channel=b.channel,
            account_id=b.account_id,
            domain=b.domain,
            created_at=b.created_at,
            updated_at=b.updated_at,
        )

    @staticmethod
    def _grant_to_dto(g: DomainGrantConfig) -> DomainGrantConfigDTO:
        return DomainGrantConfigDTO(
            domain=g.domain,
            allow_write=g.allow_write,
            allow_recall=g.allow_recall,
            allow_proactive=g.allow_proactive,
            allow_egress=g.allow_egress,
        )

    def set_binding(
        self, req: SetConnectorDomainRequest
    ) -> ConnectorDomainBindingDTO:
        """Bind a connector to a data domain."""
        binding = self.registry.set_binding(
            connector_id=req.connector_id,
            domain=req.domain,
            channel=req.channel,
            account_id=req.account_id,
        )
        return self._binding_to_dto(binding)

    def get_binding(
        self, connector_id: str
    ) -> ConnectorDomainBindingDTO | None:
        """Fetch binding details for a connector."""
        b = self.registry.get_binding(connector_id)
        return self._binding_to_dto(b) if b is not None else None

    def list_bindings(
        self, domain: DataDomainDTO | None = None
    ) -> list[ConnectorDomainBindingDTO]:
        """List connector bindings with optional domain filter."""
        items = self.registry.list_bindings(domain=domain)
        return [self._binding_to_dto(b) for b in items]

    def remove_binding(self, connector_id: str) -> bool:
        """Remove a connector binding."""
        return self.registry.remove_binding(connector_id)

    def resolve_domain(self, connector_id: str) -> DataDomainDTO:
        """Resolve connector domain; default 'work'."""
        return self.registry.resolve_domain(connector_id)

    def get_grant(self, domain: DataDomainDTO) -> DomainGrantConfigDTO:
        """Get grant configuration for a domain."""
        g = self.registry.get_grant(domain)
        return self._grant_to_dto(g)

    def list_grants(self) -> list[DomainGrantConfigDTO]:
        """List grant configurations for both work and personal domains."""
        return [
            self.get_grant("work"),
            self.get_grant("personal"),
        ]

    def update_grant(
        self, domain: DataDomainDTO, req: UpdateDomainGrantRequest
    ) -> DomainGrantConfigDTO:
        """Update permissions for a specific domain."""
        updated = self.registry.update_grant(
            domain=domain,
            allow_write=req.allow_write,
            allow_recall=req.allow_recall,
            allow_proactive=req.allow_proactive,
            allow_egress=req.allow_egress,
        )
        return self._grant_to_dto(updated)

    def validate_recall(
        self, req: ValidateRecallRequestDTO
    ) -> ValidateRecallResponseDTO:
        """Validate whether memory recall crosses domain boundaries."""
        allowed, reason, is_cross = self.guard.validate_recall(
            target_domain=req.target_domain,
            active_domain=req.active_domain,
            allow_cross_domain=req.allow_cross_domain,
        )
        return ValidateRecallResponseDTO(
            allowed=allowed,
            reason=reason,
            is_cross_domain=is_cross,
        )

    def validate_write(
        self, req: ValidateWriteRequestDTO
    ) -> ValidateWriteResponseDTO:
        """Validate whether memory write is permitted for a domain."""
        allowed, reason = self.guard.validate_write(domain=req.domain)
        return ValidateWriteResponseDTO(
            allowed=allowed,
            reason=reason,
        )

    def evaluate_egress(
        self, req: EvaluateEgressRequestDTO
    ) -> EgressDecisionDTO:
        """Evaluate outbound channel egress privacy redlines."""
        decision: EgressDecision = self.guard.evaluate_egress(
            content_domain=req.content_domain,
            target_channel=req.target_channel,
            user_confirmed=req.user_confirmed,
        )
        return EgressDecisionDTO(
            allowed=decision.allowed,
            requires_user_confirmation=decision.requires_user_confirmation,
            reason=decision.reason,
            source_domain=decision.source_domain,
            target_channel=decision.target_channel,
            is_cross_domain=decision.is_cross_domain,
        )
