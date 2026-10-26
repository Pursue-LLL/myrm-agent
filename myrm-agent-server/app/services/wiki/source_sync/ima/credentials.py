"""Encrypted storage of the ima client id / API key.

[INPUT]
- app.services.config.service::config_service (POS: UserConfig with server-side encryption of ``*Credentials`` keys)

[OUTPUT]
- load_credentials / save_credentials / clear_credentials / mask_client_id

[POS]
Credentials are account-level (shared by every agent scope) and live under ``imaCredentials``. The key is
deliberately NOT part of the public ``ConfigKey`` set: the generic config endpoints return decrypted values,
so the only way to read it back is through the dedicated ima API, which exposes a masked state only.
"""

from __future__ import annotations

from app.services.config.service import config_service

from .models import ImaCredentials

CREDENTIALS_KEY = "imaCredentials"
_DEVICE_ID = "ima-connector"


async def load_credentials() -> ImaCredentials | None:
    record = await config_service.get(CREDENTIALS_KEY)
    if record is None:
        return None
    client_id = str(record.value.get("client_id") or "").strip()
    api_key = str(record.value.get("api_key") or "").strip()
    return ImaCredentials(client_id=client_id, api_key=api_key) if client_id and api_key else None


async def save_credentials(credentials: ImaCredentials) -> None:
    await config_service.set(
        CREDENTIALS_KEY,
        {"client_id": credentials.client_id, "api_key": credentials.api_key},
        device_id=_DEVICE_ID,
    )


async def clear_credentials() -> bool:
    return await config_service.delete(CREDENTIALS_KEY)


def mask_client_id(client_id: str) -> str:
    """Enough of the id to recognise the account, never the whole value."""
    return client_id if len(client_id) <= 8 else f"{client_id[:4]}…{client_id[-4:]}"
