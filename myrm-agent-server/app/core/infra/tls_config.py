"""Enterprise TLS configuration bridge.

[INPUT]
- app.services.config.service::config_service (POS: 配置核心业务逻辑服务)
- myrm_agent_harness.infra.tls_compat (POS: Enterprise TLS compatibility)

[OUTPUT]
- apply_tls_config_from_db(): Load TLS setting from DB at startup
- sync_tls_env_from_config(): Runtime TLS toggle handler

[POS]
Server-level bridge that reads enterpriseTlsCompat from personalSettings
and syncs it to the harness-level MYRM_TLS_STRICT environment variable.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_TLS_STRICT_ENV = "MYRM_TLS_STRICT"


async def apply_tls_config_from_db() -> None:
    """Read TLS compat setting from DB and apply at startup.

    Only activates if the env var is not already set (env takes precedence).
    """
    if os.environ.get(_TLS_STRICT_ENV, "").strip():
        return

    from app.services.config.service import config_service

    record = await config_service.get("personalSettings")
    if record is None:
        return

    value = record.value if hasattr(record, "value") else {}
    if not isinstance(value, dict):
        return

    if value.get("enterpriseTlsCompat") is True:
        os.environ[_TLS_STRICT_ENV] = "0"
        from myrm_agent_harness.infra.tls_compat import apply_global_tls_relaxation

        if apply_global_tls_relaxation():
            logger.info("[TLS] Enterprise compatibility enabled from user config")


def sync_tls_env_from_config(personal_settings: dict[str, object]) -> None:
    """Update TLS env var when personalSettings changes at runtime.

    Called from config router after personalSettings write.
    """
    enabled = personal_settings.get("enterpriseTlsCompat") is True

    if enabled:
        os.environ[_TLS_STRICT_ENV] = "0"
        from myrm_agent_harness.infra.tls_compat import apply_global_tls_relaxation

        apply_global_tls_relaxation()
        logger.info("[TLS] Enterprise compatibility toggled ON via WebUI")
    else:
        os.environ.pop(_TLS_STRICT_ENV, None)
        logger.info("[TLS] Enterprise compatibility toggled OFF via WebUI")
