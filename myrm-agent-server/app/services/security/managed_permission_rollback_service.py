"""Service layer for Managed Permission Template Presets, Session Checkpoint Rollback, and Connectors Hub.

[POS] app/services/security/managed_permission_rollback_service.py
[INPUT] app.schemas.managed_permission_rollback, myrm_agent_harness.core.security.managed_permission_rollback
[OUTPUT] ManagedPermissionRollbackService, get_managed_permission_rollback_service
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.core.security.managed_permission_rollback import (
    ConnectorChannelType,
    EnterprisePermissionPresetRegistry,
    EnterpriseRoleTemplate,
    ManagedConnectorsHub,
    PermissionActionRule,
    SessionCheckpointRollbackEngine,
)

from app.schemas.managed_permission_rollback import (
    ComplianceDriftCheckRequest,
    ComplianceDriftItemDTO,
    ComplianceDriftResponse,
    CreateSessionCheckpointRequest,
    ManagedConnectorMetaDTO,
    RegisterConnectorRequest,
    RolePermissionPolicyDTO,
    RollbackSessionCheckpointRequest,
    RollbackSessionCheckpointResponse,
    SessionCheckpointDTO,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


class ManagedPermissionRollbackService:
    """Service coordinating role permission templates, checkpoint rollback engine, and connectors hub."""

    def __init__(self) -> None:
        self._preset_registry = EnterprisePermissionPresetRegistry()
        self._checkpoint_engine = SessionCheckpointRollbackEngine()
        self._connectors_hub = ManagedConnectorsHub()

    def list_presets(self) -> list[RolePermissionPolicyDTO]:
        """Return all available canonical enterprise permission templates."""
        presets = self._preset_registry.list_presets()
        return [
            RolePermissionPolicyDTO(
                role=p.role.value,
                display_name=p.display_name,
                description=p.description,
                rules={k: v.value for k, v in p.rules.items()},
                max_network_egress_domains=p.max_network_egress_domains,
                allow_shell_execution=p.allow_shell_execution,
                require_hitl_on_external_sends=p.require_hitl_on_external_sends,
                allowed_filesystem_roots=list(p.allowed_filesystem_roots),
            )
            for p in presets
        ]

    def get_preset(self, role: str) -> RolePermissionPolicyDTO:
        """Fetch canonical permission policy definition for the specified role."""
        policy = self._preset_registry.get_preset(EnterpriseRoleTemplate(role))
        return RolePermissionPolicyDTO(
            role=policy.role.value,
            display_name=policy.display_name,
            description=policy.description,
            rules={k: v.value for k, v in policy.rules.items()},
            max_network_egress_domains=policy.max_network_egress_domains,
            allow_shell_execution=policy.allow_shell_execution,
            require_hitl_on_external_sends=policy.require_hitl_on_external_sends,
            allowed_filesystem_roots=list(policy.allowed_filesystem_roots),
        )

    def check_compliance_drift(
        self, request: ComplianceDriftCheckRequest
    ) -> ComplianceDriftResponse:
        """Evaluate privilege drift against designated template baseline."""
        typed_rules: dict[str, PermissionActionRule] = {
            k: PermissionActionRule(v) for k, v in request.active_rules.items()
        }
        report = self._preset_registry.evaluate_compliance_drift(
            agent_id=request.agent_id,
            assigned_role=EnterpriseRoleTemplate(request.assigned_role),
            active_rules=typed_rules,
            active_allow_shell=request.active_allow_shell,
        )

        deviation_dtos: list[ComplianceDriftItemDTO] = [
            ComplianceDriftItemDTO(
                target=d.target,
                template_rule=d.template_rule,
                actual_rule=d.actual_rule,
                is_excessive=d.is_excessive,
                remediation_hint=d.remediation_hint,
            )
            for d in report.deviations
        ]

        return ComplianceDriftResponse(
            agent_id=report.agent_id,
            assigned_role=report.assigned_role.value,
            is_compliant=report.is_compliant,
            drift_score=report.drift_score,
            deviations=deviation_dtos,
        )

    def create_checkpoint(
        self, request: CreateSessionCheckpointRequest
    ) -> SessionCheckpointDTO:
        """Capture an immutable atomic state snapshot of workspace files and memory."""
        files_bytes: dict[str, bytes] = {
            path: content.encode("utf-8")
            for path, content in request.files.items()
        }

        ckpt = self._checkpoint_engine.create_checkpoint(
            session_id=request.session_id,
            label=request.label,
            files=files_bytes,
            memory_state=request.memory_state,
            active_role=EnterpriseRoleTemplate(request.active_role),
        )

        return SessionCheckpointDTO(
            checkpoint_id=ckpt.checkpoint_id,
            session_id=ckpt.session_id,
            label=ckpt.label,
            created_at=ckpt.created_at,
            files_count=len(ckpt.file_snapshots),
            memory_keys_count=len(ckpt.memory_state),
            active_role=ckpt.active_role.value,
        )

    def list_checkpoints(self, session_id: str) -> list[SessionCheckpointDTO]:
        """List all historical checkpoints recorded for a specific session."""
        checkpoints = self._checkpoint_engine.list_checkpoints(session_id)
        return [
            SessionCheckpointDTO(
                checkpoint_id=c.checkpoint_id,
                session_id=c.session_id,
                label=c.label,
                created_at=c.created_at,
                files_count=len(c.file_snapshots),
                memory_keys_count=len(c.memory_state),
                active_role=c.active_role.value,
            )
            for c in checkpoints
        ]

    def rollback_checkpoint(
        self, request: RollbackSessionCheckpointRequest
    ) -> RollbackSessionCheckpointResponse:
        """Roll back workspace files and memory state to targeted checkpoint."""
        current_files_bytes: dict[str, bytes] = {
            path: content.encode("utf-8")
            for path, content in request.current_files.items()
        }

        diff, restored_files_bytes, restored_memory = self._checkpoint_engine.rollback_to_checkpoint(
            checkpoint_id=request.checkpoint_id,
            current_files=current_files_bytes,
        )

        restored_files_str: dict[str, str] = {
            path: content.decode("utf-8", errors="replace")
            for path, content in restored_files_bytes.items()
        }

        return RollbackSessionCheckpointResponse(
            checkpoint_id=diff.checkpoint_id,
            session_id=diff.session_id,
            reverted_files_count=diff.reverted_files_count,
            restored_memory_keys_count=diff.restored_memory_keys_count,
            modified_paths=diff.modified_paths,
            rolled_back_at=diff.rolled_back_at,
            restored_files=restored_files_str,
            restored_memory_state=restored_memory,
        )

    def register_connector(
        self, request: RegisterConnectorRequest
    ) -> ManagedConnectorMetaDTO:
        """Register or renew an external ecosystem connector."""
        meta = self._connectors_hub.register_connector(
            connector_id=request.connector_id,
            channel_type=ConnectorChannelType(request.channel_type),
            display_name=request.display_name,
            account_identifier=request.account_identifier,
            token_lifetime_seconds=request.token_lifetime_seconds,
        )

        return ManagedConnectorMetaDTO(
            connector_id=meta.connector_id,
            channel_type=meta.channel_type.value,
            display_name=meta.display_name,
            status=meta.status.value,
            last_heartbeat_at=meta.last_heartbeat_at,
            token_expires_at=meta.token_expires_at,
            account_identifier=meta.account_identifier,
        )

    def record_connector_heartbeat(
        self, connector_id: str
    ) -> ManagedConnectorMetaDTO | None:
        """Record active heartbeat and evaluate connector token status."""
        meta = self._connectors_hub.record_heartbeat(connector_id)
        if meta is None:
            return None

        return ManagedConnectorMetaDTO(
            connector_id=meta.connector_id,
            channel_type=meta.channel_type.value,
            display_name=meta.display_name,
            status=meta.status.value,
            last_heartbeat_at=meta.last_heartbeat_at,
            token_expires_at=meta.token_expires_at,
            account_identifier=meta.account_identifier,
        )

    def list_connectors(self) -> list[ManagedConnectorMetaDTO]:
        """List all managed ecosystem connectors and their health posture."""
        connectors = self._connectors_hub.list_connectors()
        return [
            ManagedConnectorMetaDTO(
                connector_id=c.connector_id,
                channel_type=c.channel_type.value,
                display_name=c.display_name,
                status=c.status.value,
                last_heartbeat_at=c.last_heartbeat_at,
                token_expires_at=c.token_expires_at,
                account_identifier=c.account_identifier,
            )
            for c in connectors
        ]


_service_instance: ManagedPermissionRollbackService | None = None


def get_managed_permission_rollback_service() -> ManagedPermissionRollbackService:
    """Return the global ManagedPermissionRollbackService singleton instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ManagedPermissionRollbackService()
    return _service_instance
