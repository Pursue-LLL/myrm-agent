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

logger = logging.getLogger(__name__)

_refresh_locks: dict[str, asyncio.Lock] = {}


async def refresh_oauth_token(issuer: str) -> EphemeralUserCredential | None:
    """Auto-refresh an expired OAuth2 token with DB persistence, encryption and concurrency locks.

    Protects against concurrent token refresh stampedes (preventing Refresh Token Rotation lockouts).
    """
    lock = _refresh_locks.setdefault(issuer, asyncio.Lock())
    async with lock:
        async with get_session() as db_session:
            row = (
                (await db_session.execute(select(UserConfig).where(UserConfig.config_key == "oauthCredentials")))
                .scalars()
                .first()
            )

            if not row:
                logger.warning("refresh_oauth_token: 'oauthCredentials' config not found in DB")
                return None

            service = get_encryption_service()
            credentials_dict = row.config_value
            if row.is_encrypted:
                if isinstance(credentials_dict, str):
                    credentials_dict = service.decrypt(credentials_dict)
                elif isinstance(credentials_dict, dict) and "_cipher" in credentials_dict:
                    credentials_dict = service.decrypt(credentials_dict["_cipher"])

            if isinstance(credentials_dict, str):
                import json

                try:
                    credentials_dict = json.loads(credentials_dict)
                except Exception:
                    credentials_dict = {}

            if not isinstance(credentials_dict, dict) or issuer not in credentials_dict:
                logger.warning("refresh_oauth_token: no credentials for '%s'", issuer)
                return None

            cred_val = credentials_dict[issuer]
            if not isinstance(cred_val, dict):
                return None

            # Double-Checked Locking:
            # If another parallel coroutine refreshed this token while we were waiting for the lock,
            # its expires_at will be greater than now + 300s. We can use it directly!
            expires_at = cred_val.get("expires_at")
            if expires_at is not None and expires_at > time.time() + 300:
                logger.info(
                    "refresh_oauth_token: Token for '%s' was already refreshed by a parallel task. Skipping HTTP POST.",
                    issuer,
                )
                return EphemeralUserCredential(
                    issuer=issuer,
                    token=str(cred_val.get("token", "")),
                    scope=str(cred_val.get("scope", "")),
                    user_id=str(cred_val.get("user_id", "")),
                    expires_at=expires_at,
                    refresh_callback=lambda: refresh_oauth_token(issuer),
                )

            refresh_token = cred_val.get("refresh_token")
            token_url = cred_val.get("token_url")
            client_id = cred_val.get("client_id")
            client_secret = cred_val.get("client_secret")

            if not refresh_token or not token_url:
                logger.warning(
                    "refresh_oauth_token: missing refresh_token or token_url for '%s'",
                    issuer,
                )
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
                        expires_in = res_json.get("expires_in", 3600)

                        if not new_token:
                            logger.error("refresh_oauth_token: response did not contain 'access_token'")
                            return None

                        # Update and persist
                        updated_cred = dict(cred_val)
                        updated_cred["token"] = new_token
                        updated_cred["refresh_token"] = new_refresh
                        updated_cred["expires_at"] = time.time() + expires_in

                        credentials_dict[issuer] = updated_cred

                        enc_value, is_enc = service.encrypt_if_needed(
                            "oauthCredentials", credentials_dict,
                        )
                        final_value = {"_cipher": enc_value} if is_enc and isinstance(enc_value, str) else enc_value

                        row.config_value = final_value
                        from sqlalchemy.orm.attributes import flag_modified

                        flag_modified(row, "config_value")
                        await db_session.commit()

                        logger.info(
                            "refresh_oauth_token: successfully refreshed and saved token for '%s'",
                            issuer,
                        )
                        return EphemeralUserCredential(
                            issuer=issuer,
                            token=new_token,
                            scope=str(updated_cred.get("scope", "")),
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
            except Exception as exc:
                logger.error("refresh_oauth_token: failed to refresh token for '%s': %s", issuer, exc)

    return None
