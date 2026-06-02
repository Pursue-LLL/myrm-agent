"""Matrix authentication, session creation, and initial sync helpers.

[INPUT]
- mautrix.client::Client (POS: mautrix Matrix client)
- mautrix.api::HTTPAPI (POS: Matrix HTTP API layer)

[OUTPUT]
- create_aiohttp_session: Create aiohttp session with optional proxy
- authenticate: Token-based or password-based Matrix login
- initial_sync: First /sync to populate room state and DM cache
- refresh_dm_cache: Update DM room cache in-place from m.direct account data

[POS]
Extracted auth/init helpers for MatrixChannel. Handles aiohttp session
creation (with HTTP/SOCKS proxy support), token validation via whoami,
password login, initial /sync, invite processing, and m.direct DM cache
(in-place mutation for runtime refresh on auto-join).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.channels.core.exceptions import ChannelAuthError

logger = logging.getLogger(__name__)

_CRYPTO_STORE_DIR_NAME = "matrix"


def get_store_dir() -> Path:
    """Resolve the crypto store directory based on environment."""
    import os

    base = Path(os.environ.get("MYRM_DATA_DIR", Path.home() / ".myrm"))
    return base / _CRYPTO_STORE_DIR_NAME


def create_aiohttp_session(proxy: str = "") -> object:
    """Create an aiohttp.ClientSession with optional proxy configuration."""
    import aiohttp

    if not proxy:
        return aiohttp.ClientSession(trust_env=True)

    if proxy.split("://")[0].lower().startswith("socks"):
        try:
            from aiohttp_socks import ProxyConnector

            return aiohttp.ClientSession(
                connector=ProxyConnector.from_url(proxy, rdns=True),
            )
        except ImportError:
            logger.warning(
                "aiohttp_socks not installed — SOCKS proxy %s ignored. "
                "Run: pip install aiohttp-socks",
                proxy,
            )
            return aiohttp.ClientSession(trust_env=True)

    return aiohttp.ClientSession(proxy=proxy)


async def authenticate(
    client: object,
    api: object,
    session: object,
    *,
    access_token: str,
    user_id: str,
    password: str,
    device_id: str,
) -> tuple[str, str]:
    """Authenticate with the homeserver. Returns (resolved_user_id, resolved_access_token).

    Supports token-based (whoami) and password-based login flows.
    Closes the session and raises ChannelAuthError on failure.
    """
    from mautrix.client import Client
    from mautrix.types import UserID

    if not isinstance(client, Client):
        raise ChannelAuthError("Invalid client type", channel="matrix")

    if access_token:
        api.token = access_token  # type: ignore[union-attr]
        try:
            resp = await client.whoami()
            resolved_user_id = getattr(resp, "user_id", "") or user_id
            resolved_device_id = getattr(resp, "device_id", "")
            if resolved_user_id:
                user_id = str(resolved_user_id)
                client.mxid = UserID(user_id)

            effective_device_id = device_id or resolved_device_id
            if effective_device_id:
                client.device_id = effective_device_id

            logger.info(
                "Matrix: authenticated via access token (user=%s, device=%s)",
                user_id or "(unknown)",
                effective_device_id or "(auto)",
            )
            return user_id, access_token
        except Exception as exc:
            await session.close()  # type: ignore[union-attr]
            raise ChannelAuthError(
                f"Matrix whoami failed: {exc}", channel="matrix"
            ) from exc

    if password and user_id:
        try:
            resp = await client.login(
                identifier=user_id,
                password=password,
                device_name="Myrm Agent",
                device_id=device_id or None,
            )
            if resp and hasattr(resp, "device_id"):
                client.device_id = resp.device_id
            resolved_token = access_token
            if resp and hasattr(resp, "access_token"):
                resolved_token = str(resp.access_token)
            logger.info("Matrix: authenticated via password (user=%s)", user_id)
            return user_id, resolved_token
        except Exception as exc:
            await session.close()  # type: ignore[union-attr]
            raise ChannelAuthError(
                f"Matrix login failed: {exc}", channel="matrix"
            ) from exc

    await session.close()  # type: ignore[union-attr]
    raise ChannelAuthError(
        "Matrix: need access_token or user_id + password",
        channel="matrix",
    )


async def initial_sync(
    client: object,
    joined_rooms: set[str],
    dm_rooms: dict[str, bool],
    encryption: bool,
    auto_join_fn: object,
) -> None:
    """Perform initial /sync to populate room state, process invites, and share keys."""
    from mautrix.client import Client

    if not isinstance(client, Client):
        return

    try:
        sync_data = await client.sync(timeout=10000, full_state=True)
        if isinstance(sync_data, dict):
            rooms_join = sync_data.get("rooms", {}).get("join", {})
            joined_rooms.clear()
            joined_rooms.update(rooms_join.keys())

            nb = sync_data.get("next_batch")
            if nb:
                await client.sync_store.put_next_batch(nb)

            try:
                tasks = client.handle_sync(sync_data)
                if tasks:
                    await asyncio.gather(*tasks)
            except Exception as exc:
                logger.warning("Matrix: initial sync event dispatch error: %s", exc)

            invites = sync_data.get("rooms", {}).get("invite", {})
            if isinstance(invites, dict) and callable(auto_join_fn):
                for room_id in invites:
                    await auto_join_fn(client, room_id)  # type: ignore[misc]

            logger.info(
                "Matrix: initial sync complete, joined %d rooms",
                len(joined_rooms),
            )

        await refresh_dm_cache(client, joined_rooms, dm_rooms)

    except Exception as exc:
        logger.warning("Matrix: initial sync error: %s", exc)

    if encryption and getattr(client, "crypto", None):
        try:
            await client.crypto.share_keys()
        except Exception as exc:
            logger.warning("Matrix: initial key share failed: %s", exc)


async def refresh_dm_cache(
    client: object,
    joined_rooms: set[str],
    dm_rooms: dict[str, bool],
) -> None:
    """Update dm_rooms dict in-place from m.direct account data."""
    from mautrix.client import Client
    from mautrix.types import EventType as MxEventType

    if not isinstance(client, Client):
        return

    try:
        dm_data = await client.get_account_data(MxEventType.find("m.direct"))
        if isinstance(dm_data, dict):
            dm_room_ids: set[str] = set()
            for room_list in dm_data.values():
                if isinstance(room_list, list):
                    dm_room_ids.update(str(r) for r in room_list)
            dm_rooms.clear()
            dm_rooms.update(
                {room_id: room_id in dm_room_ids for room_id in joined_rooms}
            )
            logger.info(
                "Matrix: DM cache built (%d DMs / %d rooms)",
                sum(1 for v in dm_rooms.values() if v),
                len(dm_rooms),
            )
    except Exception as exc:
        logger.debug("Matrix: could not load m.direct data: %s", exc)
