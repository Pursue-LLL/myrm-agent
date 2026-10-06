"""Service layer managing admin authentication surface configuration.

[INPUT]
- myrm_agent_harness.core.security.admin_auth_surface::AdminAuthSurfaceManager (POS: Lifecycle manager enforcing safe configuration updates)
- app.schemas.admin_auth_surface::AdminAuthSurfaceConfigDto (POS: Configuration DTO for admin auth surface)

[OUTPUT]
- AdminAuthSurfaceService: Manages authentication surface configuration, anti-lockout validation, and atomic disk persistence.

[POS]
Service layer bridging admin authentication surface governance and local volume persistence to FastAPI routers.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from myrm_agent_harness.core.security.admin_auth_surface import (
    AdminAuthSurfaceConfig,
    AdminAuthSurfaceManager,
    AdminAuthSurfaceValidator,
    AuthSurfaceValidationResult,
    LoginMethodSettings,
    OAuthConnectionConfig,
    OAuthProviderType,
)

from app.schemas.admin_auth_surface import (
    AdminAuthSurfaceConfigDto,
    AuthSurfaceValidationResultDto,
    LoginMethodSettingsDto,
    OAuthConnectionDto,
    UpdateAuthSurfaceRequest,
    UpdateAuthSurfaceResponse,
)

logger = logging.getLogger(__name__)


class AdminAuthSurfaceService:
    """Service providing authentication surface governance and anti-lockout security."""

    def __init__(
        self,
        manager: AdminAuthSurfaceManager | None = None,
        storage_path: Path | str | None = None,
    ) -> None:
        """Initialize service with manager instance and persistent storage path."""
        self._lock = threading.Lock()
        if storage_path is not None:
            self._storage_path: Path | None = Path(storage_path).resolve()
        else:
            base_dir = Path(os.path.expanduser("~/.myrm"))
            self._storage_path = (base_dir / "admin_auth_surface.json").resolve()

        if manager is not None:
            self._manager = manager
        else:
            loaded_config = self._load_persisted()
            self._manager = AdminAuthSurfaceManager(initial_config=loaded_config)

    def _load_persisted(self) -> AdminAuthSurfaceConfig | None:
        """Load configuration from local storage if available."""
        if self._storage_path is None or not self._storage_path.exists():
            return None
        try:
            content = self._storage_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                return None
            dto = AdminAuthSurfaceConfigDto(**data)
            return self._to_harness(dto)
        except Exception as exc:
            logger.warning("Failed to load persisted admin auth surface: %s", exc)
            return None

    def _save_persisted(self, cfg: AdminAuthSurfaceConfig) -> None:
        """Atomically persist current configuration to disk."""
        if self._storage_path is None:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            dto = self._to_dto(cfg)
            content = json.dumps(dto.model_dump(), indent=2, ensure_ascii=False)
            temp_path = self._storage_path.with_suffix(".tmp")
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(self._storage_path)
        except Exception as exc:
            logger.error("Failed to persist admin auth surface config: %s", exc)

    def get_auth_surface(self, masked: bool = True) -> AdminAuthSurfaceConfigDto:
        """Retrieve current authentication surface configuration."""
        with self._lock:
            cfg = (
                self._manager.get_masked_config()
                if masked
                else self._manager.get_config()
            )
            return self._to_dto(cfg)

    def validate_auth_surface(
        self, config_dto: AdminAuthSurfaceConfigDto
    ) -> AuthSurfaceValidationResultDto:
        """Validate candidate configuration against anti-lockout rules."""
        harness_cfg = self._to_harness(config_dto)
        validation: AuthSurfaceValidationResult = AdminAuthSurfaceValidator.validate(
            harness_cfg
        )
        return AuthSurfaceValidationResultDto(
            is_valid=validation.is_valid,
            active_login_method_count=validation.active_login_method_count,
            errors=list(validation.errors),
            warnings=list(validation.warnings),
        )

    def update_auth_surface(
        self, request: UpdateAuthSurfaceRequest
    ) -> UpdateAuthSurfaceResponse:
        """Validate, apply, and persist new authentication surface configuration."""
        logger.info(
            "Updating admin authentication surface (preserve_secrets=%s)",
            request.preserve_masked_secrets,
        )
        candidate_harness = self._to_harness(request.config)
        with self._lock:
            applied_cfg, validation = self._manager.update_config(
                candidate_config=candidate_harness,
                preserve_masked_secrets=request.preserve_masked_secrets,
            )
            self._save_persisted(applied_cfg)
            masked_applied = self._manager.get_masked_config()

        return UpdateAuthSurfaceResponse(
            config=self._to_dto(masked_applied),
            validation=AuthSurfaceValidationResultDto(
                is_valid=validation.is_valid,
                active_login_method_count=validation.active_login_method_count,
                errors=list(validation.errors),
                warnings=list(validation.warnings),
            ),
        )

    @staticmethod
    def _to_dto(cfg: AdminAuthSurfaceConfig) -> AdminAuthSurfaceConfigDto:
        return AdminAuthSurfaceConfigDto(
            login_methods=LoginMethodSettingsDto(
                password_enabled=cfg.login_methods.password_enabled,
                email_code_enabled=cfg.login_methods.email_code_enabled,
                email_code_auto_registration_enabled=(
                    cfg.login_methods.email_code_auto_registration_enabled
                ),
            ),
            oauth_connections=[
                OAuthConnectionDto(
                    id=c.id,
                    provider=c.provider.value,  # type: ignore[arg-type]
                    name=c.name,
                    client_id=c.client_id,
                    client_secret=c.client_secret,
                    authorize_url=c.authorize_url,
                    token_url=c.token_url,
                    scopes=list(c.scopes),
                    issuer_url=c.issuer_url,
                    enabled=c.enabled,
                    auto_registration_enabled=c.auto_registration_enabled,
                )
                for c in cfg.oauth_connections
            ],
            allow_public_registration=cfg.allow_public_registration,
            mfa_enforced=cfg.mfa_enforced,
        )

    @staticmethod
    def _to_harness(dto: AdminAuthSurfaceConfigDto) -> AdminAuthSurfaceConfig:
        return AdminAuthSurfaceConfig(
            login_methods=LoginMethodSettings(
                password_enabled=dto.login_methods.password_enabled,
                email_code_enabled=dto.login_methods.email_code_enabled,
                email_code_auto_registration_enabled=(
                    dto.login_methods.email_code_auto_registration_enabled
                ),
            ),
            oauth_connections=[
                OAuthConnectionConfig(
                    id=c.id,
                    provider=OAuthProviderType(c.provider),
                    name=c.name,
                    client_id=c.client_id,
                    client_secret=c.client_secret,
                    authorize_url=c.authorize_url,
                    token_url=c.token_url,
                    scopes=list(c.scopes),
                    issuer_url=c.issuer_url,
                    enabled=c.enabled,
                    auto_registration_enabled=c.auto_registration_enabled,
                )
                for c in dto.oauth_connections
            ],
            allow_public_registration=dto.allow_public_registration,
            mfa_enforced=dto.mfa_enforced,
        )


_service_instance: AdminAuthSurfaceService | None = None


def get_admin_auth_surface_service() -> AdminAuthSurfaceService:
    """Dependency injector for AdminAuthSurfaceService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AdminAuthSurfaceService()
    return _service_instance
