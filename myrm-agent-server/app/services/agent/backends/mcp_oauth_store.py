"""MCP OAuth token store — encrypted DB persistence.

Business-layer implementation of the harness ``MCPOAuthTokenStore`` protocol.
Stores MCP OAuth tokens in the ``UserConfig`` table under the key
``mcpOAuthTokens``, encrypted via ``ConfigEncryptionService``.

Supports concurrent-safe token refresh: lock-per-server prevents Refresh
Token Rotation lockout, and a global persist lock serializes read-modify-write
of the shared token dict across servers (agent startup refreshes many servers
concurrently).

[INPUT]
- myrm_agent_harness.toolkits.mcp.oauth (POS: MCPOAuthTokenStore protocol)
- app.database (POS: DB session + UserConfig ORM model)
- app.services.config.encryption (POS: encryption service)
- app.services.integrations.oauth_store (POS: oauthCredentials 加密读写、共享行锁与加密写回原语)

[OUTPUT]
- DatabaseMCPOAuthTokenStore: concrete MCPOAuthTokenStore for DB persistence

[POS]
MCP OAuth token encrypted persistence. Implements framework MCPOAuthTokenStore
protocol with AES-256-GCM encryption, stampede-safe token refresh, and
cross-server atomic writes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import cast

import httpx
from myrm_agent_harness.toolkits.mcp.oauth import (
    MCPOAuthConfig,
    MCPOAuthToken,
)
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import UserConfig
from app.services.integrations.oauth_store import (
    decrypt_oauth_credentials,
    persist_credentials_locked,
)

logger = logging.getLogger(__name__)

_CONFIG_KEY = "mcpOAuthTokens"

_refresh_locks: dict[str, asyncio.Lock] = {}

# Serializes read-modify-write of the shared token dict across servers.
# Per-server ``_refresh_locks`` cannot prevent cross-server lost updates when
# multiple servers refresh concurrently (e.g. agent startup after expiry).
_persist_lock = asyncio.Lock()


class DatabaseMCPOAuthTokenStore:
    """Encrypted DB-backed MCP OAuth token store.

    All tokens for all MCP servers are stored under a single ``UserConfig``
    row (key=``mcpOAuthTokens``) as a dict[server_name → token_dict],
    encrypted at rest.
    """

    async def _load_tokens(self) -> dict[str, dict[str, object]]:
        async with get_session() as db:
            row = (
                (
                    await db.execute(
                        select(UserConfig).where(UserConfig.config_key == _CONFIG_KEY)
                    )
                )
                .scalars()
                .first()
            )
            if not row:
                return {}
            data = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
            return cast(dict[str, dict[str, object]], data)

    async def _save_tokens(self, tokens: dict[str, dict[str, object]]) -> None:
        async with get_session() as db:
            row = (
                (
                    await db.execute(
                        select(UserConfig).where(UserConfig.config_key == _CONFIG_KEY)
                    )
                )
                .scalars()
                .first()
            )
            await persist_credentials_locked(
                db, row, tokens, config_key=_CONFIG_KEY
            )

    async def get_token(self, server_name: str) -> MCPOAuthToken | None:
        tokens = await self._load_tokens()
        data = tokens.get(server_name)
        if not data or not isinstance(data, dict):
            return None
        try:
            token_data = {k: v for k, v in data.items() if not k.startswith("_")}
            return MCPOAuthToken(**token_data)
        except Exception:
            logger.warning("Corrupt MCP OAuth token for '%s', ignoring", server_name)
            return None

    async def save_token(self, server_name: str, token: MCPOAuthToken) -> None:
        """Persist a token for the given MCP server.

        Skips the write when the server was removed concurrently, so an
        in-flight refresh cannot resurrect a disconnected server.
        """
        async with _persist_lock:
            tokens = await self._load_tokens()
            if server_name not in tokens:
                # The server was disconnected while the refresh request was in
                # flight; drop the write-back to keep the disconnect effective.
                return
            entry = tokens.get(server_name)
            existing_config = (
                entry.get("_oauth_config") if isinstance(entry, dict) else None
            )
            data = token.model_dump()
            if existing_config:
                data["_oauth_config"] = existing_config
            tokens[server_name] = data
            await self._save_tokens(tokens)
        logger.info("Saved MCP OAuth token for '%s'", server_name)

    async def save_token_with_config(
        self, server_name: str, token: MCPOAuthToken, oauth_config: MCPOAuthConfig
    ) -> None:
        """Persist token together with the OAuth server config for later refresh."""
        async with _persist_lock:
            tokens = await self._load_tokens()
            data = token.model_dump()
            data["_oauth_config"] = {
                "token_endpoint": oauth_config.token_endpoint,
                "client_id": oauth_config.client_id,
                "client_secret": oauth_config.client_secret,
            }
            tokens[server_name] = data
            await self._save_tokens(tokens)
        logger.info("Saved MCP OAuth token+config for '%s'", server_name)

    async def get_oauth_config(self, server_name: str) -> MCPOAuthConfig | None:
        """Retrieve stored OAuth config for a server (for token refresh)."""
        tokens = await self._load_tokens()
        entry = tokens.get(server_name)
        if not isinstance(entry, dict):
            return None
        cfg_data = entry.get("_oauth_config")
        if not isinstance(cfg_data, dict) or not cfg_data.get("token_endpoint"):
            return None
        return MCPOAuthConfig(
            authorization_endpoint="",
            token_endpoint=cfg_data["token_endpoint"],
            client_id=cfg_data["client_id"],
            client_secret=cfg_data.get("client_secret"),
        )

    async def delete_token(self, server_name: str) -> None:
        async with _persist_lock:
            tokens = await self._load_tokens()
            if server_name in tokens:
                del tokens[server_name]
                await self._save_tokens(tokens)
                logger.info("Deleted MCP OAuth token for '%s'", server_name)

    async def refresh_token_exchange(
        self, server_name: str, oauth_config: MCPOAuthConfig, refresh_token: str
    ) -> MCPOAuthToken | None:
        """Exchange refresh token with stampede protection."""
        lock = _refresh_locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            existing = await self.get_token(server_name)
            if existing and not existing.is_expired:
                return existing

            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": oauth_config.client_id,
            }
            if oauth_config.client_secret:
                data["client_secret"] = oauth_config.client_secret

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(oauth_config.token_endpoint, data=data)
                    if resp.status_code != 200:
                        logger.error(
                            "MCP OAuth refresh failed for '%s': %d %s",
                            server_name,
                            resp.status_code,
                            resp.text[:200],
                        )
                        return None

                    body = resp.json()
                    new_token = MCPOAuthToken(
                        access_token=body["access_token"],
                        token_type=body.get("token_type", "Bearer"),
                        refresh_token=body.get("refresh_token") or refresh_token,
                        expires_at=time.time() + int(body.get("expires_in") or 3600),
                        scope=body.get("scope"),
                    )
                    await self.save_token(server_name, new_token)
                    if await self.get_token(server_name) is None:
                        logger.info(
                            "MCP OAuth token refresh dropped for '%s': server was disconnected",
                            server_name,
                        )
                        return None
                    logger.info("MCP OAuth token refreshed for '%s'", server_name)
                    return new_token
            except Exception:
                logger.error(
                    "MCP OAuth refresh request failed for '%s'",
                    server_name,
                    exc_info=True,
                )
                return None

    async def list_connected_servers(self) -> list[str]:
        """Return names of all MCP servers with stored OAuth tokens."""
        tokens = await self._load_tokens()
        return list(tokens.keys())

    async def get_all_statuses(self) -> dict[str, dict[str, object]]:
        """Return OAuth status for all servers: {name: {connected, expired, scope}}."""
        tokens = await self._load_tokens()
        result: dict[str, dict[str, object]] = {}
        for name, data in tokens.items():
            if not isinstance(data, dict):
                continue
            try:
                token_data = {k: v for k, v in data.items() if not k.startswith("_")}
                token = MCPOAuthToken(**token_data)
                result[name] = {
                    "connected": True,
                    "expired": token.is_expired,
                    "scope": token.scope,
                }
            except Exception:
                result[name] = {"connected": False, "expired": True, "scope": None}
        return result


_store_instance: DatabaseMCPOAuthTokenStore | None = None


def get_mcp_oauth_token_store() -> DatabaseMCPOAuthTokenStore:
    """Singleton accessor."""
    global _store_instance
    if _store_instance is None:
        _store_instance = DatabaseMCPOAuthTokenStore()
    return _store_instance
