"""Import competitor API keys into user provider config (opt-in, local only).

[INPUT]
app.services.migration.env_secrets (POS: which variables count as keys, and how a .env is read);
app.services.config.service (POS: 配置核心业务逻辑); myrm_agent_harness BUILTIN_PROVIDER_ROUTE_SEGMENT

[OUTPUT]
import_external_source_secrets(): merge detected .env keys into providers config, creating the provider rows a key alone
makes usable; returns the imported variable names and the names left alone with the reason (SecretsImportResult)

[POS]
Server business layer — explicit user-consented secret migration from external assistant installs. What counts as a key
is decided once in ``env_secrets`` (the same list the migration preview uses), so the import brings what the wizard
announced and names everything it did not bring.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from myrm_agent_harness.agent.config import BUILTIN_PROVIDER_ROUTE_SEGMENT

from app.config.deploy_mode import is_local_mode
from app.services.config.service import config_service
from app.services.migration.env_secrets import (
    ENV_TO_PROVIDER_ID,
    IMPORTABLE_PROVIDERS,
    MULTI_ENDPOINT_PROVIDERS,
    read_env_keys,
)

# Why a key variable was left alone: no provider in Myrm takes it (``unsupported``), or its provider offers several
# endpoints and the user has no row for it yet, so the key's endpoint is theirs to choose (``needs_endpoint``).
SkipReason = Literal["unsupported", "needs_endpoint"]


@dataclass(frozen=True)
class SkippedKey:
    """A key variable the import left alone: its name (never its value) and why."""

    name: str
    reason: SkipReason


@dataclass(frozen=True)
class SecretsImportResult:
    imported_keys: list[str]
    skipped_keys: list[SkippedKey]


def _find_slot(providers: list[dict[str, object]], provider_id: str) -> dict[str, object] | None:
    """The row the provider's key belongs in: the one with its id, or one the user routes through it."""
    return next((row for row in providers if provider_id in (row.get("id"), row.get("routingProfile"))), None)


def _new_provider(provider_id: str) -> dict[str, object]:
    row: dict[str, object] = {
        "id": provider_id,
        "name": IMPORTABLE_PROVIDERS[provider_id],
        "routingProfile": BUILTIN_PROVIDER_ROUTE_SEGMENT[provider_id],
        "isEnabled": True,
    }
    if provider_id == "vercel_ai_gateway":
        row["apiUrl"] = "https://ai-gateway.vercel.sh/v1"
    return row


def _put_key(row: dict[str, object], secret: str) -> None:
    """Make ``secret`` the row's active key (the first one, when it already has some) and enable the row."""
    api_keys = row.get("apiKeys")
    if isinstance(api_keys, list) and api_keys and isinstance(api_keys[0], dict):
        api_keys[0]["key"] = secret
        api_keys[0]["isActive"] = True
    else:
        row["apiKeys"] = [
            {
                "id": str(uuid.uuid4()),
                "key": secret,
                "remark": "Imported from external source migration",
                "isActive": True,
            }
        ]
    row["isEnabled"] = True


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


async def import_external_source_secrets(root: Path) -> SecretsImportResult:
    """Read the competitor ``.env`` and merge its importable API keys into the providers config."""

    if not is_local_mode():
        msg = "Secret import requires local or Tauri deployment mode"
        raise ValueError(msg)

    env_path = root / ".env"
    if not env_path.is_file():
        return SecretsImportResult(imported_keys=[], skipped_keys=[])

    keys = read_env_keys(env_path)
    unsupported = [SkippedKey(name, "unsupported") for name in keys.unsupported]
    if not keys.importable:
        return SecretsImportResult(imported_keys=[], skipped_keys=unsupported)

    record = await config_service.get("providers")
    config_version: str | None = None
    config_value: dict[str, object] = {"providers": []}
    if record is not None:
        config_version = record.version
        if not isinstance(record.value, dict):
            msg = "Providers config is not an object"
            raise ValueError(msg)
        config_value = record.value

    providers_raw = config_value.get("providers")
    providers: list[dict[str, object]] = (
        [row for row in providers_raw if isinstance(row, dict)] if isinstance(providers_raw, list) else []
    )

    imported: list[str] = []
    needs_endpoint: list[SkippedKey] = []
    for env_name, secret in keys.importable.items():
        provider_id = ENV_TO_PROVIDER_ID[env_name]
        row = _find_slot(providers, provider_id)
        if row is None:
            if provider_id in MULTI_ENDPOINT_PROVIDERS:
                needs_endpoint.append(SkippedKey(env_name, "needs_endpoint"))
                continue
            row = _new_provider(provider_id)
            providers.append(row)
        _put_key(row, secret)
        imported.append(env_name)

    if imported:
        config_value["providers"] = providers
        await config_service.set(
            "providers",
            config_value,
            device_id="competitor-migration",
            expected_version=config_version,
        )

    return SecretsImportResult(imported_keys=imported, skipped_keys=[*needs_endpoint, *unsupported])
