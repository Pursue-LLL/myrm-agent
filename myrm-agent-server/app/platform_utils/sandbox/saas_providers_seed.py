"""Seed SaaS sandbox WebUI providers with platform lite model when unset.

[INPUT]
- os.environ (POS: Read LITE_MODEL and PLATFORM_OPENROUTER_KEY from environment)
- Database connection via SQLAlchemy (POS: Read/write provider config)

[OUTPUT]
- seed_providers_if_needed(): idempotent seeding of platform model provider

[POS]
When a new SaaS sandbox starts, the WebUI has no model providers configured.
This module seeds a platform-managed OpenRouter provider so users can chat
immediately without manual configuration.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_PLATFORM_PROVIDER_ID = "platform-openrouter"
_SAAS_SEED_DEVICE_ID = "saas-platform-seed"


def _parse_lite_model_ref(model_ref: str) -> tuple[str, str] | None:
    """Parse ``openrouter/provider/model`` into provider type and model id."""
    parts = model_ref.strip().split("/", 2)
    if len(parts) != 3 or parts[0] != "openrouter":
        return None
    return parts[0], f"{parts[1]}/{parts[2]}"


async def seed_saas_platform_providers_if_needed() -> None:
    """On sandbox boot, ensure defaultModelConfig points at platform lite model."""
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    if get_deploy_mode() != DeployMode.SANDBOX:
        return

    lite_ref = os.getenv("MYRM_SAAS_DEFAULT_LITE_MODEL", "").strip()
    ingress = os.getenv("CP_PUBLIC_INGRESS_URL", "").strip().rstrip("/")
    if not lite_ref or not ingress:
        return

    parsed = _parse_lite_model_ref(lite_ref)
    if parsed is None:
        logger.warning("Invalid MYRM_SAAS_DEFAULT_LITE_MODEL: %s", lite_ref)
        return
    provider_type, model_id = parsed
    relay_api_url = f"{ingress}/llm-relay/v1"

    from app.services.config.service import ConfigService

    service = ConfigService()
    record = await service.get("providers")
    existing_value: dict[str, object] = {}
    if record is not None and isinstance(record.value, dict):
        existing_value = dict(record.value)

    default_cfg = existing_value.get("defaultModelConfig")
    if isinstance(default_cfg, dict):
        base = default_cfg.get("baseModel")
        if isinstance(base, dict) and isinstance(base.get("primary"), dict):
            if base["primary"].get("model"):
                return

    selection = {"providerId": _PLATFORM_PROVIDER_ID, "model": model_id}
    providers_payload: dict[str, object] = {
        "providers": [
            {
                "id": _PLATFORM_PROVIDER_ID,
                "providerType": provider_type,
                "isEnabled": True,
                "apiKeys": [{"key": "platform-managed", "isActive": True}],
                "apiUrl": relay_api_url,
                "enabledModels": [model_id],
            }
        ],
        "defaultModelConfig": {
            "baseModel": {"primary": selection},
            "liteModel": {"primary": selection},
        },
    }

    if record is not None:
        merged = dict(existing_value)
        merged["providers"] = providers_payload["providers"]
        merged["defaultModelConfig"] = providers_payload["defaultModelConfig"]
        await service.set("providers", merged, _SAAS_SEED_DEVICE_ID, record.version)
    else:
        await service.set("providers", providers_payload, _SAAS_SEED_DEVICE_ID)

    logger.info("Seeded SaaS platform lite model config: %s", model_id)
