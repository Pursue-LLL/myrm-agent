"""Unified session credential assembly for agent execution paths.

[INPUT]
- app.core.channel_bridge.config_loader::UserConfigs (OAuth + providers)
- app.channels.storage::CredentialsStore (channel tokens)
- app.services.agent.platform_config::resolve_xai_search_config (xAI provider key)

[OUTPUT]
- assemble_session_credentials: build EphemeralUserCredential tuple for user_credentials_ctx
- session_credentials_scope: inject credentials for a context block
- user_config_session_credentials_scope: load WebUI user configs then inject credentials
- XAI_ISSUER: canonical issuer key for xAI provider API keys

[POS]
Single assembly point for Web stream, channel bridge, cron runner, and other agent entry paths.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from myrm_agent_harness.agent.security import EphemeralUserCredential

logger = logging.getLogger(__name__)

XAI_ISSUER = "xai"


async def _oauth_credentials_from_dict(
    oauth_credentials_dict: dict[str, object] | None,
) -> list[EphemeralUserCredential]:
    if not oauth_credentials_dict:
        return []

    from app.services.agent.oauth_refresher import refresh_oauth_token

    credentials: list[EphemeralUserCredential] = []
    for issuer, cred_val in oauth_credentials_dict.items():
        if not isinstance(cred_val, dict) or "token" not in cred_val:
            continue
        issuer_str = str(issuer)
        # xAI convention: EphemeralUserCredential.scope carries base_url
        # (consistent with _xai_provider_credentials which sets scope=base_url)
        if issuer_str == XAI_ISSUER:
            scope = str(cred_val.get("base_url", ""))
        else:
            scope = str(cred_val.get("scope", ""))
        credentials.append(
            EphemeralUserCredential(
                issuer=issuer_str,
                token=str(cred_val["token"]),
                scope=scope,
                user_id=str(cred_val.get("user_id", "")),
                expires_at=cred_val.get("expires_at"),  # type: ignore[arg-type]
                refresh_callback=lambda i=issuer_str: refresh_oauth_token(i),
            )
        )
    return credentials


def _xai_provider_credentials(
    providers_dict: dict[str, object] | None,
) -> list[EphemeralUserCredential]:
    from app.services.agent.platform_config import resolve_xai_search_config

    resolved = resolve_xai_search_config(providers_dict)
    if not resolved:
        return []

    api_key, base_url = resolved
    return [
        EphemeralUserCredential(
            issuer=XAI_ISSUER,
            token=api_key,
            scope=base_url,
        )
    ]


async def _channel_token_credentials(channel: str) -> list[EphemeralUserCredential]:
    from app.channels.storage import CredentialsStore

    store = CredentialsStore()
    creds_dict = await store.get(channel)
    if not creds_dict:
        return []

    token = creds_dict.get("user_access_token") or creds_dict.get("access_token")
    if not token:
        return []

    async def _channel_token_refresher() -> EphemeralUserCredential | None:
        logger.info("Channel token refresher callback triggered for '%s'", channel)
        fresh_creds = await store.get(channel)
        if not fresh_creds:
            return None
        fresh_token = fresh_creds.get("user_access_token") or fresh_creds.get("access_token")
        if not fresh_token:
            return None
        return EphemeralUserCredential(
            issuer=channel,
            token=str(fresh_token),
            user_id=str(fresh_creds.get("user_id", "")),
            refresh_callback=_channel_token_refresher,
        )

    return [
        EphemeralUserCredential(
            issuer=channel,
            token=str(token),
            user_id=str(creds_dict.get("user_id", "")),
            refresh_callback=_channel_token_refresher,
        )
    ]


async def assemble_session_credentials(
    *,
    oauth_credentials_dict: dict[str, object] | None = None,
    providers_dict: dict[str, object] | None = None,
    channel: str | None = None,
) -> tuple[EphemeralUserCredential, ...]:
    """Build merged session credentials for user_credentials_ctx injection.

    xAI credential priority: OAuth token (from SuperGrok login) takes precedence
    over API Key (from WebUI providers). If both exist, only the OAuth credential
    is included for the xAI issuer to avoid duplicate entries.
    """
    credentials: list[EphemeralUserCredential] = []
    try:
        oauth_creds = await _oauth_credentials_from_dict(oauth_credentials_dict)
        credentials.extend(oauth_creds)

        has_xai_oauth = any(c.issuer == XAI_ISSUER for c in oauth_creds)
        if not has_xai_oauth:
            credentials.extend(_xai_provider_credentials(providers_dict))

        if channel:
            credentials.extend(await _channel_token_credentials(channel))
    except Exception as exc:
        logger.warning("Failed to assemble session credentials: %s", exc)
    return tuple(credentials)


@asynccontextmanager
async def session_credentials_scope(
    *,
    oauth_credentials_dict: dict[str, object] | None = None,
    providers_dict: dict[str, object] | None = None,
    channel: str | None = None,
) -> AsyncIterator[None]:
    """Inject assembled session credentials for the duration of the context block."""
    from myrm_agent_harness.agent.security import user_credentials_ctx

    credentials = await assemble_session_credentials(
        oauth_credentials_dict=oauth_credentials_dict,
        providers_dict=providers_dict,
        channel=channel,
    )
    token_ctx = user_credentials_ctx.set(credentials)
    try:
        yield
    finally:
        user_credentials_ctx.reset(token_ctx)


@asynccontextmanager
async def user_config_session_credentials_scope(
    *,
    channel: str | None = None,
) -> AsyncIterator[None]:
    """Load WebUI user configs and inject session credentials for the block."""
    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    async with session_credentials_scope(
        oauth_credentials_dict=configs.oauth_credentials_dict if configs else None,
        providers_dict=configs.providers_dict if configs else None,
        channel=channel,
    ):
        yield
