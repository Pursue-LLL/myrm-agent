"""Service for Mechanical Credential Isolation and Zero-Context Secret Replacement.

[INPUT]
- Secret credentials, target egress hosts, outbound payloads, and operation parameter dicts.

[OUTPUT]
- DTO models representing handles, egress substitution results, and atomic grant lifecycle transitions.

[POS]
- Server security service. Wraps harness secret_broker subsystem for REST API consumption.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.core.security.secret_broker import (
    AtomicOperationGrantManager,
    BoundSecretHandle,
    EgressBoundSecretVault,
    EgressSecretInterceptor,
)

from app.schemas.secret_broker import (
    AtomicGrantDto,
    BoundSecretHandleDto,
    ResolveEgressResponse,
)


class SecretBrokerService:
    """Singleton service managing egress-bound credentials and one-shot operation grants."""

    def __init__(self) -> None:
        self._vault = EgressBoundSecretVault()
        self._interceptor = EgressSecretInterceptor(self._vault)
        self._grant_manager = AtomicOperationGrantManager()

    def ingest_secret(
        self,
        secret_name: str,
        secret_value: str,
        allowed_host: str,
    ) -> BoundSecretHandleDto:
        """Securely store credential and return an opaque reference handle."""
        handle: BoundSecretHandle = self._vault.ingest_secret(
            secret_name=secret_name,
            secret_value=secret_value,
            allowed_host=allowed_host,
        )
        return BoundSecretHandleDto(
            handle_id=handle.handle_id,
            secret_name=handle.secret_name,
            placeholder=handle.placeholder,
            allowed_host=handle.allowed_host,
            created_at=handle.created_at,
        )

    def list_handles(self) -> list[BoundSecretHandleDto]:
        """List all registered secret handles."""
        handles = self._vault.list_handles()
        return [
            BoundSecretHandleDto(
                handle_id=h.handle_id,
                secret_name=h.secret_name,
                placeholder=h.placeholder,
                allowed_host=h.allowed_host,
                created_at=h.created_at,
            )
            for h in handles
        ]

    def get_handle(self, handle_id: str) -> BoundSecretHandleDto | None:
        """Get public handle metadata."""
        h = self._vault.get_handle(handle_id)
        if not h:
            return None
        return BoundSecretHandleDto(
            handle_id=h.handle_id,
            secret_name=h.secret_name,
            placeholder=h.placeholder,
            allowed_host=h.allowed_host,
            created_at=h.created_at,
        )

    def resolve_egress(self, content: str, target_host: str) -> ResolveEgressResponse:
        """Perform outbound placeholder replacement verified against egress destination host."""
        res = self._interceptor.inject_secrets(content, target_host)
        return ResolveEgressResponse(
            resolved_content=res.resolved_content,
            replacements_count=res.replacements_count,
            target_host=res.target_host,
            authorized=res.authorized,
        )

    def create_grant(
        self,
        operation_name: str,
        payload: dict[str, str | int | float | bool | list[str]],
        ttl_seconds: float = 180.0,
    ) -> AtomicGrantDto:
        """Create a new one-shot atomic grant for an operation with parameter hash binding."""
        payload_hash = self._grant_manager.compute_payload_hash(payload)
        grant = self._grant_manager.create_grant(
            operation_name=operation_name,
            payload_hash=payload_hash,
            ttl_seconds=ttl_seconds,
        )
        return AtomicGrantDto(
            grant_id=grant.grant_id,
            operation_name=grant.operation_name,
            payload_hash=grant.payload_hash,
            status=grant.status.value,
            created_at=grant.created_at,
            expires_at=grant.expires_at,
        )

    def approve_grant(self, grant_id: str) -> AtomicGrantDto:
        """Approve an atomic operation grant."""
        grant = self._grant_manager.approve_grant(grant_id)
        return AtomicGrantDto(
            grant_id=grant.grant_id,
            operation_name=grant.operation_name,
            payload_hash=grant.payload_hash,
            status=grant.status.value,
            created_at=grant.created_at,
            expires_at=grant.expires_at,
        )

    def reject_grant(self, grant_id: str, reason: str = "User denied operation") -> AtomicGrantDto:
        """Terminally reject and revoke an operation grant."""
        grant = self._grant_manager.reject_grant(grant_id, reason)
        return AtomicGrantDto(
            grant_id=grant.grant_id,
            operation_name=grant.operation_name,
            payload_hash=grant.payload_hash,
            status=grant.status.value,
            created_at=grant.created_at,
            expires_at=grant.expires_at,
        )

    def consume_grant(
        self,
        grant_id: str,
        operation_name: str,
        payload: dict[str, str | int | float | bool | list[str]],
    ) -> bool:
        """Consume an approved operation grant. Invalidate if mutated."""
        payload_hash = self._grant_manager.compute_payload_hash(payload)
        return self._grant_manager.consume_grant(grant_id, operation_name, payload_hash)

    def get_grant(self, grant_id: str) -> AtomicGrantDto | None:
        """Get an existing grant by ID."""
        grant = self._grant_manager.get_grant(grant_id)
        if not grant:
            return None
        return AtomicGrantDto(
            grant_id=grant.grant_id,
            operation_name=grant.operation_name,
            payload_hash=grant.payload_hash,
            status=grant.status.value,
            created_at=grant.created_at,
            expires_at=grant.expires_at,
        )

    def list_grants(self) -> list[AtomicGrantDto]:
        """List all operation grants."""
        grants = self._grant_manager.list_grants()
        return [
            AtomicGrantDto(
                grant_id=g.grant_id,
                operation_name=g.operation_name,
                payload_hash=g.payload_hash,
                status=g.status.value,
                created_at=g.created_at,
                expires_at=g.expires_at,
            )
            for g in grants
        ]


_service_lock = threading.Lock()
_global_secret_broker_service: SecretBrokerService | None = None


def get_secret_broker_service() -> SecretBrokerService:
    """Retrieve or initialize the global SecretBrokerService singleton."""
    global _global_secret_broker_service
    if _global_secret_broker_service is None:
        with _service_lock:
            if _global_secret_broker_service is None:
                _global_secret_broker_service = SecretBrokerService()
    return _global_secret_broker_service
