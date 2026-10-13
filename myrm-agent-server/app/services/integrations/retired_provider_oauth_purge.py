"""Purge credentials left behind by the retired in-process subscription logins.

[INPUT]
- app.services.integrations.oauth_store (POS: oauthCredentials blob read/write under the shared row lock)

[OUTPUT]
- RETIRED_PROVIDER_ISSUERS: oauthCredentials issuers written by the removed Claude / ChatGPT / GitHub Copilot logins
- purge_retired_provider_credentials: drop those issuers from the stored blob

[POS]
Startup data hygiene. Nothing reads or refreshes these issuers any more, so the
stored OAuth tokens would otherwise stay encrypted-at-rest forever with no way to
disconnect them from the UI.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.integrations.oauth_store import (
    decrypt_oauth_credentials,
    load_oauth_credentials_row,
    oauth_credentials_lock,
    persist_credentials_locked,
)

logger = logging.getLogger(__name__)

RETIRED_PROVIDER_ISSUERS: tuple[str, ...] = (
    "provider_anthropic",
    "provider_openai",
    "provider_copilot",
)


async def purge_retired_provider_credentials(db: AsyncSession) -> int:
    """Remove retired provider issuers from oauthCredentials; return how many were removed.

    The blob is rewritten only when at least one retired issuer is present, so the
    call is idempotent and a blob that cannot be parsed is never overwritten.
    """
    async with oauth_credentials_lock:
        row = await load_oauth_credentials_row(db)
        if not row:
            return 0

        credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
        retired = [issuer for issuer in RETIRED_PROVIDER_ISSUERS if issuer in credentials]
        if not retired:
            return 0

        for issuer in retired:
            del credentials[issuer]
        await persist_credentials_locked(db, row, credentials)

    logger.info("Purged OAuth credentials of retired provider issuers: %s", ", ".join(retired))
    return len(retired)
