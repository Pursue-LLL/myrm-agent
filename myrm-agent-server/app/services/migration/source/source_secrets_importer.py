"""Import competitor API keys into user provider config (opt-in, local only).

[INPUT]
source_payload_loader env key names; app.services.config.service (POS: 配置核心业务逻辑);
myrm_agent_harness transport PROFILES (POS: the key variables each provider reads) and BUILTIN_PROVIDER_ROUTE_SEGMENT

[OUTPUT]
import_external_source_secrets(): merge detected .env keys into providers config; seed minimal provider stubs when none exist

[POS]
Server business layer — explicit user-consented secret migration from external assistant installs. The variables read
are the ones the transport itself reads for a provider (so a key a competitor's ``.env`` shares with us is found by the
same name) plus the aliases competitors use; only providers a key alone makes usable are imported, never one that also
needs an endpoint the ``.env`` does not carry (Azure, Bedrock, any provider reached through a shared OpenAI endpoint).
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from dotenv import dotenv_values
from myrm_agent_harness.agent.config.provider_routing import BUILTIN_PROVIDER_ROUTE_SEGMENT
from myrm_agent_harness.toolkits.llms.transport.profile import PROFILES

from app.config.deploy_mode import is_local_mode
from app.services.config.service import config_service

# The providers a key alone makes usable, with their settings-UI display names (the frontend's ``providerCatalog.ts``).
_IMPORTABLE_PROVIDERS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "zai": "Z.AI (Zhipu AI)",
    "xai": "xAI",
    "ollama": "Ollama",
    "moonshot": "Moonshot AI",
    "lm_studio": "LM Studio",
    "groq": "Groq",
    "dashscope": "Dashscope (Qwen)",
    "minimax": "MiniMax",
    "mistral": "Mistral AI",
    "together_ai": "Together AI",
    "volcengine": "Doubao (Volcengine)",
    "fireworks_ai": "Fireworks AI",
    "perplexity": "Perplexity AI",
    "xiaomi_mimo": "Xiaomi MiMo",
    "vercel_ai_gateway": "Vercel AI Gateway",
}

# The key variables come from the transport's own table; Vercel's gateway has no profile of its own (it is reached
# through the OpenAI wire at a fixed endpoint), so its variables are named here.
_ENV_TO_PROVIDER_ID: dict[str, str] = {
    env: provider_id
    for provider_id in _IMPORTABLE_PROVIDERS
    if provider_id in PROFILES
    for env in PROFILES[provider_id].api_key_env
}
_ENV_TO_PROVIDER_ID.update(
    {
        # Variable names other assistants use for a provider the transport names differently
        # (documented in Hermes Agent's ``.env.example``).
        "GLM_API_KEY": "zai",
        "KIMI_API_KEY": "moonshot",
        "XIAOMI_API_KEY": "xiaomi_mimo",
        "AI_GATEWAY_API_KEY": "vercel_ai_gateway",
        "VERCEL_AI_GATEWAY_KEY": "vercel_ai_gateway",
        "VERCEL_API_KEY": "vercel_ai_gateway",
    }
)


def _read_env_secrets(env_path: Path) -> dict[str, str]:
    """The importable keys of a ``.env`` file, read by python-dotenv's grammar (quotes, ``export``, comments).

    Nothing is interpolated: ``${NAME}`` would otherwise read this process's environment into the result, and a
    reference left unresolved is not a key, so it is skipped.
    """
    try:
        content = env_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}

    values = dotenv_values(stream=io.StringIO(content), interpolate=False)
    secrets: dict[str, str] = {}
    for name, raw in values.items():
        value = (raw or "").strip()
        if name in _ENV_TO_PROVIDER_ID and value and "${" not in value:
            secrets[name] = value
    return secrets


def _minimal_provider_stub(provider_id: str, secret_value: str) -> dict[str, object]:
    stub: dict[str, object] = {
        "id": provider_id,
        "name": _IMPORTABLE_PROVIDERS[provider_id],
        "routingProfile": BUILTIN_PROVIDER_ROUTE_SEGMENT[provider_id],
        "isEnabled": True,
        "apiKeys": [
            {
                "id": str(uuid.uuid4()),
                "key": secret_value,
                "remark": "Imported from external source migration",
                "isActive": True,
            }
        ],
    }
    if provider_id == "vercel_ai_gateway":
        stub["apiUrl"] = "https://ai-gateway.vercel.sh/v1"
    return stub


def _seed_provider_stubs(
    providers_raw: list[object],
    secrets: dict[str, str],
) -> list[dict[str, object]]:
    """Append minimal provider rows for env keys that have no matching slot."""

    typed: list[dict[str, object]] = [provider for provider in providers_raw if isinstance(provider, dict)]
    existing_ids = {str(provider.get("id", "")).strip() for provider in typed if str(provider.get("id", "")).strip()}
    for env_name, secret_value in secrets.items():
        provider_id = _ENV_TO_PROVIDER_ID[env_name]
        if provider_id in existing_ids:
            continue
        typed.append(_minimal_provider_stub(provider_id, secret_value))
        existing_ids.add(provider_id)
    return typed


async def external_source_providers_configured() -> bool:
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


async def import_external_source_secrets(root: Path) -> dict[str, object]:
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
    config_version: str | None = None
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
                api_keys = [
                    {
                        "id": str(uuid.uuid4()),
                        "key": secret_value,
                        "remark": "Imported from external source migration",
                        "isActive": True,
                    }
                ]
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
