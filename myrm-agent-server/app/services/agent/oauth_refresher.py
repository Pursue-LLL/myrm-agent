"""OAuth token auto-refresh service.

Handles automatic refresh of OAuth tokens for Google Workspace, xAI and
every other issuer that exposes a standard OAuth2 refresh_token grant.

[INPUT]
- app.database.models::UserConfig (POS: ORM model for user config storage)
- app.services.config.encryption (POS: sensitive config encryption/decryption)
- app.services.integrations.oauth_store (POS: oauthCredentials 加密读写、共享行锁与加密写回原语)
- app.services.agent.oauth_token_policy (POS: expiry resolution and refresh-failure classification)
- myrm_agent_harness.agent.security.types::EphemeralUserCredential (POS: session-scoped credential)

[OUTPUT]
- refresh_oauth_token: async refresh for any OAuth issuer, returns EphemeralUserCredential
- is_refresh_rejected: read-only check whether the provider permanently rejected a stored refresh token

[POS]
OAuth token refresh service. Manages token lifecycle for all OAuth-connected integrations
and model providers, with per-issuer locking, cancellation shielding, shared-row write
serialization, failure memory (rejected refresh tokens, transient cooldown) and reauth
notification.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping

import httpx
from myrm_agent_harness.agent.security.types import EphemeralUserCredential
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import UserConfig
from app.services.agent.oauth_token_policy import (
    TOKEN_REFRESH_LEAD_S,
    classify_refresh_failure,
    credential_expiry,
    refresh_token_fingerprint,
    resolve_expires_at,
)
from app.services.config.encryption import get_encryption_service
from app.services.integrations.oauth_store import (
    CONFIG_KEY,
    decrypt_oauth_credentials,
    load_oauth_credentials_row,
    oauth_credentials_lock,
    persist_credentials_locked,
)

logger = logging.getLogger(__name__)

GOOGLE_WORKSPACE_ISSUER = "google_workspace"

_refresh_locks: dict[str, asyncio.Lock] = {}
_reauth_emitted_at: dict[str, float] = {}

# Issuer -> fingerprint of the refresh token the provider rejected for good.
# Retrying a rejected (or already rotated) token cannot succeed; only a new
# login yields a different fingerprint and lifts the block.
_rejected_refresh_tokens: dict[str, str] = {}

# Issuer -> monotonic deadline before which no new refresh is attempted after a
# transient failure, so an outage is not hit once per LLM call.
_retry_not_before: dict[str, float] = {}

_REAUTH_DEDUP_WINDOW_S = 300
_TRANSIENT_COOLDOWN_S = 30.0


def is_refresh_rejected(issuer: str, credential: Mapping[str, object]) -> bool:
    """True when the provider rejected this credential's current refresh token for good.

    Reads the in-process failure memory only: no I/O, no refresh attempt. The
    memory starts empty with the process, so a rejection is reported again once
    the next refresh attempt meets it.
    """
    refresh_token = credential.get("refresh_token")
    return (
        isinstance(refresh_token, str)
        and bool(refresh_token)
        and _rejected_refresh_tokens.get(issuer) == refresh_token_fingerprint(refresh_token)
    )


def _emit_reauth_if_needed(issuer: str, reason: str) -> None:
    """Publish OAUTH_REAUTH_REQUIRED via AppEventBus with per-issuer dedup."""
    now = time.time()
    if now - _reauth_emitted_at.get(issuer, 0) < _REAUTH_DEDUP_WINDOW_S:
        return

    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    _reauth_emitted_at[issuer] = now
    try:
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.OAUTH_REAUTH_REQUIRED,
                data={"issuer": issuer, "reason": reason},
            )
        )
        logger.info(
            "Published OAUTH_REAUTH_REQUIRED for issuer '%s' (reason: %s)",
            issuer,
            reason,
        )
    except Exception as exc:
        logger.warning("Failed to publish OAUTH_REAUTH_REQUIRED: %s", exc)


def _resolve_oauth_client_credentials(
    issuer: str,
    cred_val: dict[str, object],
) -> tuple[str | None, str | None]:
    """Resolve OAuth client_id/secret for token refresh.

    Server-owned integrations (google_workspace) read from settings; user/MCP
    issuers keep credentials stored in the encrypted oauthCredentials blob.
    """
    if issuer == GOOGLE_WORKSPACE_ISSUER:
        from app.config.settings import settings

        client_id = settings.google_client_id.strip()
        client_secret = settings.google_client_secret.get_secret_value().strip()
        return (client_id or None, client_secret or None)

    stored_client_id = cred_val.get("client_id")
    stored_client_secret = cred_val.get("client_secret")
    return (
        str(stored_client_id) if stored_client_id else None,
        str(stored_client_secret) if stored_client_secret else None,
    )


async def _merge_refreshed_credential(
    *,
    issuer: str,
    updated_cred: dict[str, object],
) -> None:
    """Merge a refreshed credential into the shared oauthCredentials blob.

    Different issuers hold independent refresh locks, so a fast refresh of one
    issuer must not clobber another issuer's concurrent update. Re-reading and
    merging under the shared row lock (owned by ``oauth_store``) makes the
    read-modify-write atomic across all writers.
    """
    async with oauth_credentials_lock:
        async with get_session() as db:
            row = await load_oauth_credentials_row(db)
            credentials: dict[str, object] = {}
            if row is not None:
                credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)

            if issuer not in credentials:
                # The issuer was disconnected while the refresh HTTP request
                # was in flight; drop the write-back to honor the disconnect.
                return
            credentials[issuer] = updated_cred
            await persist_credentials_locked(db, row, credentials)


def _as_ephemeral_credential(issuer: str, cred: dict[str, object]) -> EphemeralUserCredential:
    """Wrap a stored credential entry for session-scoped use."""
    from app.services.agent.session_credential_assembler import XAI_ISSUER

    scope = cred.get("base_url") if issuer == XAI_ISSUER else cred.get("scope")
    return EphemeralUserCredential(
        issuer=issuer,
        token=str(cred.get("token", "")),
        scope=str(scope or ""),
        user_id=str(cred.get("user_id", "")),
        expires_at=credential_expiry(cred),
        refresh_callback=lambda: refresh_oauth_token(issuer),
    )


def _response_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except Exception:
        return None


def _reauth_reason(body: object) -> str:
    """Human-readable reason carried by the reauth event (provider text first)."""
    if isinstance(body, dict):
        reason = body.get("error_description") or body.get("error")
        if reason:
            return str(reason)
    return "token_expired"


def _consume_task_result(task: asyncio.Task[EphemeralUserCredential | None]) -> None:
    """Mark the outcome as retrieved: a caller cancelled mid-refresh never reads it."""
    if not task.cancelled():
        task.exception()


async def refresh_oauth_token(issuer: str) -> EphemeralUserCredential | None:
    """Auto-refresh an expired OAuth2 token with DB persistence, encryption and concurrency locks.

    Protects against concurrent token refresh stampedes (preventing Refresh Token Rotation lockouts).
    The exchange runs as its own task shielded from caller cancellation: refresh tokens are
    single-use for several issuers, so abandoning the exchange after the provider rotated the
    token would strand the account with a refresh token nobody saved.
    """
    task = asyncio.ensure_future(_refresh_serialized(issuer))
    task.add_done_callback(_consume_task_result)
    return await asyncio.shield(task)


async def _refresh_serialized(issuer: str) -> EphemeralUserCredential | None:
    lock = _refresh_locks.setdefault(issuer, asyncio.Lock())
    async with lock:
        async with get_session() as db_session:
            row = (await db_session.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))).scalars().first()

            if not row:
                logger.warning(
                    "refresh_oauth_token: '%s' config not found in DB",
                    CONFIG_KEY,
                )
                return None

            service = get_encryption_service()
            credentials_dict = decrypt_oauth_credentials(row.config_value, row.is_encrypted, service)

            if issuer not in credentials_dict:
                logger.warning("refresh_oauth_token: no credentials for '%s'", issuer)
                return None

            cred_val = credentials_dict[issuer]
            if not isinstance(cred_val, dict):
                return None

            # Double-Checked Locking:
            # If another parallel coroutine refreshed this token while we were waiting for the lock,
            # its expiry is beyond the refresh lead window. We can use it directly!
            expires_at = credential_expiry(cred_val)
            if expires_at is not None and expires_at > time.time() + TOKEN_REFRESH_LEAD_S:
                logger.info(
                    "refresh_oauth_token: Token for '%s' was already refreshed by a parallel task. Skipping HTTP POST.",
                    issuer,
                )
                return _as_ephemeral_credential(issuer, cred_val)

            refresh_token = cred_val.get("refresh_token")
            token_url = cred_val.get("token_url")
            client_id, client_secret = _resolve_oauth_client_credentials(issuer, cred_val)

            if not refresh_token or not token_url:
                logger.warning(
                    "refresh_oauth_token: missing refresh_token or token_url for '%s'",
                    issuer,
                )
                if not refresh_token:
                    _emit_reauth_if_needed(issuer, "missing_refresh_token")
                return None

            fingerprint = refresh_token_fingerprint(str(refresh_token))
            if _rejected_refresh_tokens.get(issuer) == fingerprint:
                # Keep the user informed (deduplicated) without spending another attempt.
                _emit_reauth_if_needed(issuer, "token_expired")
                return None
            if time.monotonic() < _retry_not_before.get(issuer, 0.0):
                return None

            logger.info(
                "refresh_oauth_token: executing POST request to %s for issuer '%s'",
                token_url,
                issuer,
            )
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
            if client_id:
                data["client_id"] = client_id
            if client_secret:
                data["client_secret"] = client_secret

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(token_url, data=data)
                    if response.status_code != 200:
                        body = _response_json(response)
                        logger.error(
                            "refresh_oauth_token: HTTP POST to %s failed (status %d): %s",
                            token_url,
                            response.status_code,
                            response.text,
                        )
                        if classify_refresh_failure(response.status_code, body) == "terminal":
                            _rejected_refresh_tokens[issuer] = fingerprint
                            _emit_reauth_if_needed(issuer, _reauth_reason(body))
                        else:
                            _retry_not_before[issuer] = time.monotonic() + _TRANSIENT_COOLDOWN_S
                        return None

                    res_json = response.json()
                    new_token = res_json.get("access_token")
                    new_refresh = res_json.get("refresh_token") or refresh_token

                    if not new_token:
                        logger.error("refresh_oauth_token: response did not contain 'access_token'")
                        _retry_not_before[issuer] = time.monotonic() + _TRANSIENT_COOLDOWN_S
                        return None

                    # Update and persist
                    updated_cred = dict(cred_val)
                    updated_cred["token"] = new_token
                    updated_cred["refresh_token"] = new_refresh
                    updated_cred["expires_at"] = resolve_expires_at(new_token, res_json.get("expires_in"), now=time.time())
                    if issuer == GOOGLE_WORKSPACE_ISSUER:
                        updated_cred.pop("client_id", None)
                        updated_cred.pop("client_secret", None)

                    await _merge_refreshed_credential(
                        issuer=issuer,
                        updated_cred=updated_cred,
                    )
                    _rejected_refresh_tokens.pop(issuer, None)
                    _retry_not_before.pop(issuer, None)

                    logger.info(
                        "refresh_oauth_token: successfully refreshed and saved token for '%s'",
                        issuer,
                    )
                    return _as_ephemeral_credential(issuer, updated_cred)
            except Exception as exc:
                _retry_not_before[issuer] = time.monotonic() + _TRANSIENT_COOLDOWN_S
                logger.error(
                    "refresh_oauth_token: failed to refresh token for '%s': %s",
                    issuer,
                    exc,
                )

    return None
