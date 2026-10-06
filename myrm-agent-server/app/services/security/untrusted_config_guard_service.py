"""Service layer for Untrusted Project Config Isolation and Preflight Diagnostic Gate.

[INPUT]
- Harness project isolation config resolvers and schema request DTOs.

[OUTPUT]
- UntrustedConfigGuardService providing workspace configuration resolution, validation, and trust audits.

[POS]
Service layer bridging HTTP presentation with untrusted project config isolation.
"""

from __future__ import annotations

import logging
import os
import threading

from myrm_agent_harness.config.project_isolation import (
    ConfigResolutionContext,
    DiagnosticCheckResult,
    HierarchicalConfigResolver,
    PreflightConfigValidator,
)

from app.schemas.untrusted_config_guard import (
    DiagnosticResultResponse,
    EffectiveConfigResponse,
    PreflightValidateRequest,
    ResolveConfigRequest,
)

logger = logging.getLogger(__name__)


class UntrustedConfigGuardService:
    """Manages workspace trust boundaries, hierarchical config resolution, and preflight static checks."""

    def __init__(
        self,
        resolver: HierarchicalConfigResolver | None = None,
        validator: PreflightConfigValidator | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._trusted_workspaces: set[str] = set()
        self.resolver = resolver or HierarchicalConfigResolver()
        self.validator = validator or PreflightConfigValidator()

    def set_workspace_trust(self, workspace_path: str, trusted: bool) -> bool:
        """Mark a workspace path as trusted or untrusted."""
        canonical = os.path.realpath(os.path.expanduser(workspace_path))
        with self._lock:
            if trusted:
                self._trusted_workspaces.add(canonical)
            else:
                self._trusted_workspaces.discard(canonical)
        logger.info(
            "Workspace trust updated for '%s': trusted=%s", canonical, trusted
        )
        return trusted

    def is_workspace_trusted(self, workspace_path: str) -> bool:
        """Check whether a workspace is currently marked as trusted."""
        canonical = os.path.realpath(os.path.expanduser(workspace_path))
        with self._lock:
            return canonical in self._trusted_workspaces

    def resolve_config(
        self, req: ResolveConfigRequest
    ) -> DiagnosticResultResponse:
        """Resolve effective configuration respecting workspace trust boundaries."""
        canonical = os.path.realpath(os.path.expanduser(req.workspace_path))
        # Project is trusted if explicitly declared in request OR previously recorded in trust registry
        trusted = req.is_project_trusted or self.is_workspace_trusted(canonical)

        ctx = ConfigResolutionContext(
            workspace_path=canonical,
            is_project_trusted=trusted,
            global_config_path=req.global_config_path,
        )
        result: DiagnosticCheckResult = self.resolver.resolve(ctx)
        return self._to_response(result)

    def validate_preflight(
        self, req: PreflightValidateRequest
    ) -> DiagnosticResultResponse:
        """Run preflight static schema diagnostics on raw JSON or dictionary configuration."""
        validator = PreflightConfigValidator(
            require_all_enabled=req.require_all_enabled
        )

        if req.raw_json is not None:
            result = validator.validate_json_string(req.raw_json)
        elif req.config_dict is not None:
            result = validator.validate_raw_dict(req.config_dict)
        else:
            result = validator.validate_raw_dict({})

        return self._to_response(result)

    def _to_response(
        self, result: DiagnosticCheckResult
    ) -> DiagnosticResultResponse:
        cfg = result.effective_config
        eff_resp = EffectiveConfigResponse(
            version=cfg.version,
            model_tier=cfg.model_tier,
            execution_timeout=cfg.execution_timeout,
            allow_network=cfg.allow_network,
            cache_write_read_ratio=cfg.cache_write_read_ratio,
            sandbox_enabled=cfg.sandbox_enabled,
            anti_exfiltration_guard=cfg.anti_exfiltration_guard,
            audit_logging=cfg.audit_logging,
            custom_rules=list(cfg.custom_rules),
            description=cfg.description,
        )
        return DiagnosticResultResponse(
            is_valid=result.is_valid,
            version=result.version,
            applied_tier=result.applied_tier.value,
            unknown_keys=list(result.unknown_keys),
            validation_errors=list(result.validation_errors),
            effective_config=eff_resp,
            all_mandatory_features_enabled=result.all_mandatory_features_enabled,
        )

    def clear(self) -> None:
        """Clear all workspace trust records."""
        with self._lock:
            self._trusted_workspaces.clear()


_singleton_service: UntrustedConfigGuardService | None = None


def get_untrusted_config_guard_service() -> UntrustedConfigGuardService:
    """Retrieve singleton instance of UntrustedConfigGuardService."""
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = UntrustedConfigGuardService()
    return _singleton_service
