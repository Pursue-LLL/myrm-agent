"""Import competitor API keys into user provider config (opt-in, local only).

[INPUT]
competitor_payload_loader env key names; app.services.config.service (POS: 配置核心业务逻辑)

[OUTPUT]
import_competitor_secrets(): merge detected .env keys into providers config; seed minimal provider stubs when none exist

[POS]
Server business layer — explicit user-consented secret migration from competitor installs.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config.deploy_mode import is_local_mode
from app.services.config.service import config_service

_PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "openrouter": "OpenRouter",
    "google": "Google",
    "groq": "Groq",
    "xai": "xAI",
    "mistral": "Mistral",
    "deepseek": "DeepSeek",
}

_ENV_TO_PROVIDER_ID: dict[str, str] = {
    "OPENAI_API_KEY": "openai",
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENROUTER_API_KEY": "openrouter",
    "GOOGLE_API_KEY": "google",
    "GEMINI_API_KEY": "google",
    "GROQ_API_KEY": "groq",
    "XAI_API_KEY": "xai",
    "MISTRAL_API_KEY": "mistral",
    "DEEPSEEK_API_KEY": "deepseek",
}


def _read_env_secrets(env_path: Path) -> dict[str, str]:
    secrets: dict[str, str] = {}
    try:
        content = env_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return secrets

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in _ENV_TO_PROVIDER_ID and value:
            secrets[key] = value
    return secrets


def _minimal_provider_stub(provider_id: str, secret_value: str) -> dict[str, object]:
    display = _PROVIDER_DISPLAY_NAMES.get(provider_id, provider_id)
    return {
        "id": provider_id,
        "name": display,
        "routingProfile": provider_id,
        "isEnabled": True,
        "apiKeys": [
            {
                "id": str(uuid.uuid4()),
                "key": secret_value,
                "remark": "Imported from competitor migration",
                "isActive": True,
            }
        ],
    }


def _seed_provider_stubs(
    providers_raw: list[object],
    secrets: dict[str, str],
) -> list[dict[str, object]]:
    """Append minimal provider rows for env keys that have no matching slot."""

    typed: list[dict[str, object]] = [
        provider for provider in providers_raw if isinstance(provider, dict)
    ]
    existing_ids = {
        str(provider.get("id", "")).strip()
        for provider in typed
        if str(provider.get("id", "")).strip()
    }
    for env_name, secret_value in secrets.items():
        provider_id = _ENV_TO_PROVIDER_ID[env_name]
        if provider_id in existing_ids:
            continue
        typed.append(_minimal_provider_stub(provider_id, secret_value))
        existing_ids.add(provider_id)
    return typed


async def competitor_providers_configured() -> bool:
    """Return True when at least one model provider slot exists for secret import."""

    record = await config_service.get("providers")
    if record is None:
        return False
    config_value = record.value
    if not isinstance(config_value, dict):
        return False
    providers_raw = config_value.get("providers")
    if not isinstance(providers_raw, list) or not providers_raw:
        return False
    for provider in providers_raw:
        if isinstance(provider, dict) and str(provider.get("id", "")).strip():
            return True
    return False


async def import_competitor_secrets(root: Path) -> dict[str, object]:
    """Read competitor .env and merge allowed API keys into providers config."""

    if not is_local_mode():
        msg = "Secret import requires local or Tauri deployment mode"
        raise ValueError(msg)

    env_path = root / ".env"
    if not env_path.is_file():
        return {"imported_keys": [], "skipped_keys": [], "message": "No .env file found"}

    secrets = _read_env_secrets(env_path)
    if not secrets:
        return {"imported_keys": [], "skipped_keys": [], "message": "No importable API keys in .env"}

    record = await config_service.get("providers")
    config_version: int | None = None
    if record is None:
        config_value: dict[str, object] = {"providers": []}
    else:
        config_version = record.version
        raw_value = record.value
        if not isinstance(raw_value, dict):
            return {"imported_keys": [], "skipped_keys": list(secrets.keys()), "message": "Invalid providers config"}
        config_value = raw_value

    providers_raw = config_value.get("providers")
    if not isinstance(providers_raw, list):
        providers_raw = []

    seeded = _seed_provider_stubs(providers_raw, secrets)
    config_value["providers"] = seeded
    providers_raw = seeded

    imported: list[str] = []
    skipped: list[str] = []

    for env_name, secret_value in secrets.items():
        provider_id = _ENV_TO_PROVIDER_ID[env_name]
        matched = False
        for provider in providers_raw:
            if not isinstance(provider, dict):
                continue
            if provider.get("id") != provider_id and provider.get("routingProfile") != provider_id:
                continue
            matched = True
            api_keys = provider.get("apiKeys")
            if not isinstance(api_keys, list):
                api_keys = []
            if api_keys and isinstance(api_keys[0], dict):
                api_keys[0]["key"] = secret_value
                api_keys[0]["isActive"] = True
            else:
                api_keys = [{
                    "id": str(uuid.uuid4()),
                    "key": secret_value,
                    "remark": "Imported from competitor migration",
                    "isActive": True,
                }]
            provider["apiKeys"] = api_keys
            provider["isEnabled"] = True
            imported.append(env_name)
            break
        if not matched:
            skipped.append(env_name)

    if imported:
        await config_service.set(
            "providers",
            config_value,
            device_id="competitor-migration",
            expected_version=config_version,
        )

    message = f"Imported {len(imported)} API key(s)" if imported else "No matching providers to update"
    if imported and config_version is None:
        message = f"Created provider slots and imported {len(imported)} API key(s)"

    return {
        "imported_keys": imported,
        "skipped_keys": skipped,
        "message": message,
    }
