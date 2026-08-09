"""OAuth token auto-refresh service.

Handles automatic refresh of OAuth tokens for Google Workspace, xAI,
and Provider OAuth (Anthropic, OpenAI, Copilot) credentials.
Copilot uses non-standard refresh via GitHub access_token exchange.

[INPUT]
- app.database.models::UserConfig (POS: ORM model for user config storage)
- app.services.config.encryption (POS: sensitive config encryption/decryption)
- app.services.integrations.oauth_store (POS: oauthCredentials 加密读写、共享行锁与加密写回原语；extract_copilot_base_url: Copilot JWT proxy-ep parser)
- myrm_agent_harness.agent.security::EphemeralUserCredential (POS: session-scoped credential)

[OUTPUT]
- refresh_oauth_token: async refresh for any OAuth issuer, returns EphemeralUserCredential

[POS]
OAuth token refresh service. Manages token lifecycle for all OAuth-connected integrations
and model providers, with per-issuer locking, shared-row write serialization, and reauth
notification.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from myrm_agent_harness.agent.security import EphemeralUserCredential
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import UserConfig
from app.services.config.encryption import get_encryption_service
from app.services.integrations.oauth_store import (
    CONFIG_KEY,
    decrypt_oauth_credentials,
    extract_copilot_base_url,
    load_oauth_credentials_row,
    oauth_credentials_lock,
    persist_credentials_locked,
)

logger = logging.getLogger(__name__)

GOOGLE_WORKSPACE_ISSUER = "google_workspace"
COPILOT_ISSUER = "provider_copilot"

_refresh_locks: dict[str, asyncio.Lock] = {}
_reauth_emitted_at: dict[str, float] = {}

_REAUTH_DEDUP_WINDOW_S = 300
_TOKEN_FRESH_GRACE_S = 300


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

    client_id = cred_val.get("client_id")
    client_secret = cred_val.get("client_secret")
    return (
        str(client_id) if client_id else None,
        str(client_secret) if client_secret else None,
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


async def refresh_oauth_token(issuer: str) -> EphemeralUserCredential | None:
    """Auto-refresh an expired OAuth2 token with DB persistence, encryption and concurrency locks.

    Protects against concurrent token refresh stampedes (preventing Refresh Token Rotation lockouts).
    """
    lock = _refresh_locks.setdefault(issuer, asyncio.Lock())
    async with lock:
        async with get_session() as db_session:
            row = (
                (
                    await db_session.execute(
                        select(UserConfig).where(
                            UserConfig.config_key == CONFIG_KEY
                        )
                    )
                )
                .scalars()
                .first()
            )

            if not row:
                logger.warning(
                    "refresh_oauth_token: '%s' config not found in DB",
                    CONFIG_KEY,
                )
                return None

            service = get_encryption_service()
            credentials_dict = decrypt_oauth_credentials(
                row.config_value, row.is_encrypted, service
            )

            if issuer not in credentials_dict:
                logger.warning("refresh_oauth_token: no credentials for '%s'", issuer)
                return None

            cred_val = credentials_dict[issuer]
            if not isinstance(cred_val, dict):
                return None

            # Double-Checked Locking:
            # If another parallel coroutine refreshed this token while we were waiting for the lock,
            # its expires_at will be greater than now + 300s. We can use it directly!
            expires_at = cred_val.get("expires_at")
            if expires_at is not None and expires_at > time.time() + _TOKEN_FRESH_GRACE_S:
                logger.info(
                    "refresh_oauth_token: Token for '%s' was already refreshed by a parallel task. Skipping HTTP POST.",
                    issuer,
                )
                from app.services.agent.session_credential_assembler import XAI_ISSUER

                scope = (
                    str(cred_val.get("base_url", ""))
                    if issuer == XAI_ISSUER
                    else str(cred_val.get("scope", ""))
                )
                return EphemeralUserCredential(
                    issuer=issuer,
                    token=str(cred_val.get("token", "")),
                    scope=scope,
                    user_id=str(cred_val.get("user_id", "")),
                    expires_at=expires_at,
                    refresh_callback=lambda: refresh_oauth_token(issuer),
                )

            # Copilot uses non-standard refresh: GitHub access_token → /copilot_internal/v2/token
            if issuer == COPILOT_ISSUER:
                return await _refresh_copilot_token(cred_val)

            refresh_token = cred_val.get("refresh_token")
            token_url = cred_val.get("token_url")
            client_id, client_secret = _resolve_oauth_client_credentials(
                issuer, cred_val
            )

            if not refresh_token or not token_url:
                logger.warning(
                    "refresh_oauth_token: missing refresh_token or token_url for '%s'",
                    issuer,
                )
                if not refresh_token:
                    _emit_reauth_if_needed(issuer, "missing_refresh_token")
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
                    if response.status_code == 200:
                        res_json = response.json()
                        new_token = res_json.get("access_token")
                        new_refresh = res_json.get("refresh_token") or refresh_token
                        expires_in = int(res_json.get("expires_in") or 3600)

                        if not new_token:
                            logger.error(
                                "refresh_oauth_token: response did not contain 'access_token'"
                            )
                            return None

                        # Update and persist
                        updated_cred = dict(cred_val)
                        updated_cred["token"] = new_token
                        updated_cred["refresh_token"] = new_refresh
                        updated_cred["expires_at"] = time.time() + expires_in
                        if issuer == GOOGLE_WORKSPACE_ISSUER:
                            updated_cred.pop("client_id", None)
                            updated_cred.pop("client_secret", None)

                        await _merge_refreshed_credential(
                            issuer=issuer,
                            updated_cred=updated_cred,
                        )

                        logger.info(
                            "refresh_oauth_token: successfully refreshed and saved token for '%s'",
                            issuer,
                        )
                        from app.services.agent.session_credential_assembler import (
                            XAI_ISSUER,
                        )

                        refresh_scope = (
                            str(updated_cred.get("base_url", ""))
                            if issuer == XAI_ISSUER
                            else str(updated_cred.get("scope", ""))
                        )
                        return EphemeralUserCredential(
                            issuer=issuer,
                            token=new_token,
                            scope=refresh_scope,
                            user_id=str(updated_cred.get("user_id", "")),
                            expires_at=updated_cred.get("expires_at"),
                            refresh_callback=lambda: refresh_oauth_token(issuer),
                        )
                    else:
                        logger.error(
                            "refresh_oauth_token: HTTP POST to %s failed (status %d): %s",
                            token_url,
                            response.status_code,
                            response.text,
                        )
                        if response.status_code < 500:
                            reason = "token_expired"
                            try:
                                err_body = response.json()
                                reason = (
                                    err_body.get("error_description")
                                    or err_body.get("error")
                                    or reason
                                )
                            except Exception:
                                pass
                            _emit_reauth_if_needed(issuer, str(reason))
            except Exception as exc:
                logger.error(
                    "refresh_oauth_token: failed to refresh token for '%s': %s",
                    issuer,
                    exc,
                )

    return None


async def _refresh_copilot_token(
    cred_val: dict[str, object],
) -> EphemeralUserCredential | None:
    """Refresh GitHub Copilot token using GitHub access token.

    Copilot tokens are short-lived (~30min). The refresh_token field
    stores the long-lived GitHub access token used to acquire new Copilot tokens.
    """
    github_access_token = cred_val.get("refresh_token")
    if not github_access_token:
        logger.warning(
            "refresh_copilot_token: missing GitHub access token (refresh_token)"
        )
        _emit_reauth_if_needed(COPILOT_ISSUER, "missing_github_token")
        return None

    copilot_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {github_access_token}",
        "User-Agent": "GitHubCopilotChat/0.35.0",
        "Editor-Version": "vscode/1.107.0",
        "Editor-Plugin-Version": "copilot-chat/0.35.0",
        "Copilot-Integration-Id": "vscode-chat",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers=copilot_headers,
            )
            if resp.status_code != 200:
                logger.error(
                    "refresh_copilot_token: Copilot token exchange failed (%d): %s",
                    resp.status_code,
                    resp.text,
                )
                if resp.status_code in (401, 403):
                    _emit_reauth_if_needed(COPILOT_ISSUER, "github_token_expired")
                return None

            data = resp.json()
            new_token = data.get("token")
            new_expires_at = data.get("expires_at")

            if not new_token or not isinstance(new_expires_at, (int, float)):
                logger.error("refresh_copilot_token: invalid Copilot token response")
                return None

            base_url = extract_copilot_base_url(new_token)

            updated_cred = dict(cred_val)
            updated_cred["token"] = new_token
            updated_cred["expires_at"] = float(new_expires_at)
            updated_cred["base_url"] = base_url

            await _merge_refreshed_credential(
                issuer=COPILOT_ISSUER,
                updated_cred=updated_cred,
            )

            logger.info("refresh_copilot_token: successfully refreshed Copilot token")

            return EphemeralUserCredential(
                issuer=COPILOT_ISSUER,
                token=new_token,
                scope="copilot",
                user_id="",
                expires_at=float(new_expires_at),
                refresh_callback=lambda: refresh_oauth_token(COPILOT_ISSUER),
            )
    except Exception as exc:
        logger.error("refresh_copilot_token: failed: %s", exc)

    return None
