"""Subscription (provider OAuth) token custody for LLM calls.

[INPUT]
- app.services.agent.oauth_refresher::refresh_oauth_token (POS: serialized refresh with failure memory)
- app.services.agent.oauth_token_policy (POS: due-check and expiry resolution)
- app.services.agent.session_credential_assembler::XAI_ISSUER (POS: canonical issuer key)
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials persistence)

[OUTPUT]
- PROVIDER_OAUTH_ISSUERS: provider id -> oauthCredentials issuer backing its LLM calls
- OAUTH_KEY_MARKER: placeholder api key the WebUI sends to mean "use my subscription"
- refresh_provider_oauth_credentials: renew due tokens inside a loaded oauthCredentials blob
- resolve_oauth_marker: swap the placeholder for the stored (fresh) token, host-pinned
- freshen_api_key: harness hook returning a renewed token for a key issued by this module
- ProviderOAuthUnavailableError: the subscription cannot back this request

[POS]
Single owner of which provider tokens come from the subscription store and how they
stay fresh: at config load (so every new run starts with a valid token), at LLM call
time (long-lived agents outlive one access token) and for WebUI model probes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Mapping
from typing import NamedTuple
from urllib.parse import urlparse

from app.database.connection import get_session
from app.services.agent.oauth_refresher import refresh_oauth_token
from app.services.agent.oauth_token_policy import TOKEN_REFRESH_LEAD_S, credential_expiry, is_refresh_due
from app.services.agent.session_credential_assembler import XAI_ISSUER
from app.services.integrations.oauth_store import decrypt_oauth_credentials, load_oauth_credentials_row

logger = logging.getLogger(__name__)

PROVIDER_OAUTH_ISSUERS: dict[str, str] = {"xai": XAI_ISSUER}

# Must equal ``OAUTH_AUTH_API_KEY_MARKER`` in the frontend providerTypes module;
# ``test_provider_oauth_tokens`` pins the two literals together.
OAUTH_KEY_MARKER = "__myrm_oauth_token__"

# Config loading is awaited by readiness probes with a 3 s deadline, so it only
# waits briefly; an LLM call or model probe can afford a full token exchange.
_LOAD_REFRESH_BUDGET_S = 2.0
_CALL_REFRESH_BUDGET_S = 10.0

_MAX_ISSUED_TOKENS = 16


class ProviderOAuthUnavailableError(Exception):
    """The stored subscription cannot back the requested provider call."""


class _IssuedToken(NamedTuple):
    issuer: str
    expires_at: float | None


# Access tokens this process handed out, most recent last. ``freshen_api_key``
# only acts on keys found here, so API-key users never touch the token store.
_issued_tokens: OrderedDict[str, _IssuedToken] = OrderedDict()


def _remember(issuer: str, credential: Mapping[str, object]) -> None:
    token = credential.get("token")
    if not isinstance(token, str) or not token:
        return
    _issued_tokens[token] = _IssuedToken(issuer, credential_expiry(credential))
    _issued_tokens.move_to_end(token)
    while len(_issued_tokens) > _MAX_ISSUED_TOKENS:
        _issued_tokens.popitem(last=False)


async def _load_stored_credential(issuer: str) -> dict[str, object] | None:
    async with get_session() as db:
        row = await load_oauth_credentials_row(db)
        if row is None:
            return None
        entry = decrypt_oauth_credentials(row.config_value, row.is_encrypted).get(issuer)
    return dict(entry) if isinstance(entry, dict) else None


async def _fresh_credential(issuer: str, credential: Mapping[str, object], *, budget_s: float) -> dict[str, object]:
    """Return ``credential`` with a renewed access token when it is due.

    Best effort within ``budget_s``: on timeout or failure the stored token is
    returned unchanged (the refresh keeps running and persists on its own), so
    callers carry on with the stored token instead of failing.
    """
    if not is_refresh_due(credential, now=time.time()):
        return dict(credential)
    try:
        refreshed = await asyncio.wait_for(refresh_oauth_token(issuer), timeout=budget_s)
    except TimeoutError:
        logger.warning("Subscription token refresh for '%s' exceeded %.1fs; using the stored token", issuer, budget_s)
        return dict(credential)
    except Exception:
        logger.warning("Subscription token refresh for '%s' failed; using the stored token", issuer, exc_info=True)
        return dict(credential)
    if refreshed is None:
        return dict(credential)
    renewed = {**credential, "token": refreshed.token}
    if refreshed.expires_at is not None:
        renewed["expires_at"] = refreshed.expires_at
    return renewed


async def refresh_provider_oauth_credentials(oauth_credentials: dict[str, object]) -> None:
    """Renew due subscription tokens inside a loaded oauthCredentials blob, in place."""
    for issuer in PROVIDER_OAUTH_ISSUERS.values():
        entry = oauth_credentials.get(issuer)
        if not isinstance(entry, dict) or not entry.get("token"):
            continue
        fresh = await _fresh_credential(issuer, entry, budget_s=_LOAD_REFRESH_BUDGET_S)
        oauth_credentials[issuer] = fresh
        _remember(issuer, fresh)


def _same_endpoint_host(requested: object, issued: object) -> bool:
    """True when the request targets the host the credential was issued for.

    An absent request URL means the provider's default endpoint, which is the
    issuing host. Tokens must never travel to any other host.
    """
    issued_host = urlparse(str(issued or "")).hostname
    if not issued_host:
        return False
    if not requested:
        return True
    parsed = urlparse(str(requested))
    return parsed.scheme == "https" and (parsed.hostname or "").lower() == issued_host.lower()


async def resolve_oauth_marker(model_kwargs: dict[str, object]) -> None:
    """Replace the WebUI subscription placeholder in ``api_key`` with the real token."""
    if model_kwargs.get("api_key") != OAUTH_KEY_MARKER:
        return
    provider_id = str(model_kwargs.get("model", "")).split("/", 1)[0].lower()
    issuer = PROVIDER_OAUTH_ISSUERS.get(provider_id)
    stored = await _load_stored_credential(issuer) if issuer else None
    if issuer is None or stored is None or not stored.get("token"):
        raise ProviderOAuthUnavailableError("The subscription is not connected for this provider")
    if not _same_endpoint_host(model_kwargs.get("base_url"), stored.get("base_url")):
        raise ProviderOAuthUnavailableError("The subscription can only be used with the provider's own endpoint")
    fresh = await _fresh_credential(issuer, stored, budget_s=_CALL_REFRESH_BUDGET_S)
    _remember(issuer, fresh)
    model_kwargs["api_key"] = str(fresh["token"])


async def freshen_api_key(api_key: str) -> str | None:
    """Return a renewed token for a key this module issued and that is about to expire.

    Called by the harness before each LLM request. Keys it never issued (the
    user's own API keys) and still-fresh tokens cost a dict lookup.
    """
    issued = _issued_tokens.get(api_key)
    if issued is None or issued.expires_at is None:
        return None
    if issued.expires_at - time.time() > TOKEN_REFRESH_LEAD_S:
        return None
    stored = await _load_stored_credential(issued.issuer)
    if stored is None:
        return None
    fresh = await _fresh_credential(issued.issuer, stored, budget_s=_CALL_REFRESH_BUDGET_S)
    token = fresh.get("token")
    if not isinstance(token, str) or not token or token == api_key:
        return None
    _remember(issued.issuer, fresh)
    return token
