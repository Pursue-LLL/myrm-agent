"""Matrix E2EE (End-to-End Encryption) initialization and helpers.

[INPUT]
- mautrix.client::Client (POS: mautrix Matrix client)
- mautrix.crypto::OlmMachine (POS: Olm/Megolm crypto engine)

[OUTPUT]
- check_e2ee_deps: Check if mautrix E2EE dependencies are available
- setup_e2ee: Initialize OlmMachine and attach to mautrix Client
- create_crypto_state_store: StateStore adapter for OlmMachine

[POS]
E2EE initialization for Matrix channel. Sets up OlmMachine with SQLite-backed
CryptoStore, handles device key verification, cross-signing bootstrap, and
recovery key import. Separated from channel.py for single responsibility.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_E2EE_INSTALL_HINT = "Run: uv sync --extra matrix --extra matrix-e2ee (requires libolm C library)"


def check_e2ee_deps() -> bool:
    """Return True if mautrix E2EE dependencies (python-olm) are available."""
    try:
        from mautrix.crypto import OlmMachine  # noqa: F401

        return True
    except (ImportError, AttributeError):
        return False


class CryptoStateStore:
    """Adapter that satisfies the mautrix crypto StateStore interface.

    OlmMachine requires a StateStore with ``is_encrypted``,
    ``get_encryption_info``, and ``find_shared_rooms``. We provide
    simple implementations that consult the client's room state.
    """

    def __init__(self, client_state_store: object, joined_rooms: set[str]) -> None:
        self._ss = client_state_store
        self._joined_rooms = joined_rooms

    async def is_encrypted(self, room_id: str) -> bool:
        return (await self.get_encryption_info(room_id)) is not None

    async def get_encryption_info(self, room_id: str) -> object | None:
        if hasattr(self._ss, "get_encryption_info"):
            return await self._ss.get_encryption_info(room_id)  # type: ignore[union-attr]
        return None

    async def find_shared_rooms(self, user_id: str) -> list[str]:
        return list(self._joined_rooms)


async def setup_e2ee(
    client: object,
    device_id: str,
    user_id: str,
    store_dir: Path,
    joined_rooms: set[str],
    recovery_key: str = "",
) -> bool:
    """Initialize E2EE on a mautrix Client. Returns True on success.

    Sets up:
    1. SQLite-backed CryptoStore for key persistence
    2. OlmMachine with unverified trust for maximum compatibility
    3. Device key verification against homeserver
    4. Cross-signing bootstrap or recovery key import
    """
    from mautrix.client import Client
    from mautrix.crypto import OlmMachine
    from mautrix.crypto.store.asyncpg import PgCryptoStore
    from mautrix.types import TrustState
    from mautrix.util.async_db import Database

    if not isinstance(client, Client):
        logger.error("Matrix E2EE: client is not a mautrix Client instance")
        return False

    store_dir.mkdir(parents=True, exist_ok=True)
    crypto_db_path = store_dir / "crypto.db"

    try:
        crypto_db = Database.create(
            f"sqlite:///{crypto_db_path}",
            upgrade_table=PgCryptoStore.upgrade_table,
        )
        await crypto_db.start()

        account_id = user_id or "myrm"
        pickle_key = f"{account_id}:{device_id or 'default'}"
        crypto_store = PgCryptoStore(
            account_id=account_id,
            pickle_key=pickle_key,
            db=crypto_db,
        )
        await crypto_store.open()

        if device_id:
            await crypto_store.put_device_id(device_id)

        state_store = getattr(client, "state_store", None)
        crypto_state = CryptoStateStore(state_store, joined_rooms)
        olm = OlmMachine(client, crypto_store, crypto_state)

        olm.share_keys_min_trust = TrustState.UNVERIFIED
        olm.send_keys_min_trust = TrustState.UNVERIFIED

        await olm.load()

        if not await _verify_device_keys(client, olm):
            await crypto_db.stop()
            return False

        if not await _share_keys_safely(client, olm, crypto_db):
            return False

        await _handle_cross_signing(client, olm, recovery_key)

        client.crypto = olm
        # Store reference for cleanup
        client._myrm_crypto_db = crypto_db  # type: ignore[attr-defined]

        logger.info(
            "Matrix: E2EE enabled (store: %s, device_id=%s)",
            crypto_db_path,
            device_id or "(auto)",
        )
        return True

    except Exception as exc:
        logger.error(
            "Matrix: failed to initialize E2EE: %s. %s",
            exc,
            _E2EE_INSTALL_HINT,
        )
        return False


async def _verify_device_keys(client: object, olm: object) -> bool:
    """Verify our device keys exist on the homeserver after loading crypto state."""
    from mautrix.client import Client
    from mautrix.crypto import OlmMachine

    if not isinstance(client, Client) or not isinstance(olm, OlmMachine):
        return False

    try:
        resp = await client.query_keys({client.mxid: [client.device_id]})
    except Exception as exc:
        logger.error("Matrix: cannot verify device keys: %s", exc)
        return False

    device_keys_map = getattr(resp, "device_keys", {}) or {}
    our_user_devices = device_keys_map.get(str(client.mxid)) or {}
    our_keys = our_user_devices.get(str(client.device_id))
    local_ed25519 = olm.account.identity_keys.get("ed25519")

    if not our_keys:
        logger.warning("Matrix: device keys missing from server — re-uploading")
        olm.account.shared = False
        try:
            await olm.share_keys()
        except Exception as exc:
            logger.error("Matrix: failed to re-upload device keys: %s", exc)
            return False
        return await _verify_keys_after_upload(client, local_ed25519)

    server_ed25519 = _extract_server_ed25519(our_keys)

    if server_ed25519 != local_ed25519:
        if olm.account.shared:
            logger.error(
                "Matrix: server has different identity keys for device %s — "
                "local crypto state is stale. Delete crypto.db and restart.",
                client.device_id,
            )
            return False

        logger.warning(
            "Matrix: server has stale keys for device %s — attempting re-upload",
            client.device_id,
        )
        try:
            await olm.share_keys()
        except Exception as exc:
            logger.error("Matrix: cannot upload device keys: %s", exc)
            return False
        return await _verify_keys_after_upload(client, local_ed25519)

    return True


async def _verify_keys_after_upload(client: object, local_ed25519: str | None) -> bool:
    """Re-query the server after share_keys() and verify ed25519 matches."""
    from mautrix.client import Client

    if not isinstance(client, Client):
        return False

    try:
        resp = await client.query_keys({client.mxid: [client.device_id]})
        dk = getattr(resp, "device_keys", {}) or {}
        ud = dk.get(str(client.mxid)) or {}
        dev = ud.get(str(client.device_id))
        if dev:
            server_ed = _extract_server_ed25519(dev)
            if server_ed != local_ed25519:
                logger.error(
                    "Matrix: device %s has immutable identity keys that don't match this installation.",
                    client.device_id,
                )
                return False
    except Exception as exc:
        logger.error("Matrix: post-upload key verification failed: %s", exc)
        return False
    return True


def _extract_server_ed25519(device_keys_obj: object) -> str | None:
    """Extract the ed25519 identity key from a DeviceKeys object."""
    for kid, kval in (getattr(device_keys_obj, "keys", {}) or {}).items():
        if str(kid).startswith("ed25519:"):
            return str(kval)
    return None


async def _share_keys_safely(
    client: object,
    olm: object,
    crypto_db: object,
) -> bool:
    """Share keys proactively, detecting stale OTK conflicts early."""
    from mautrix.crypto import OlmMachine

    if not isinstance(olm, OlmMachine):
        return False

    try:
        await olm.share_keys()
    except Exception as exc:
        exc_str = str(exc)
        if "already exists" in exc_str:
            logger.error(
                "Matrix: device has stale one-time keys on the server. "
                "Delete the device from the homeserver and restart, "
                "or generate a new access token."
            )
            if hasattr(crypto_db, "stop"):
                await crypto_db.stop()  # type: ignore[union-attr]
            return False
        logger.warning("Matrix: share_keys() warning during startup: %s", exc)
    return True


async def _handle_cross_signing(
    client: object,
    olm: object,
    recovery_key: str,
) -> None:
    """Import cross-signing keys from recovery key, or bootstrap if none exist."""
    from mautrix.crypto import OlmMachine

    if not isinstance(olm, OlmMachine):
        return

    if recovery_key:
        try:
            await olm.verify_with_recovery_key(recovery_key)
            logger.info("Matrix: cross-signing verified via recovery key")
        except Exception as exc:
            logger.warning("Matrix: recovery key verification failed: %s", exc)
    else:
        try:
            own_xsign = await olm.get_own_cross_signing_public_keys()
        except Exception as exc:
            own_xsign = None
            logger.warning("Matrix: cross-signing key lookup failed: %s", exc)
        if own_xsign is None:
            try:
                new_recovery_key = await olm.generate_recovery_key()
                logger.warning(
                    "Matrix: bootstrapped cross-signing. SAVE THIS RECOVERY KEY for future restarts: %s",
                    new_recovery_key,
                )
            except Exception as exc:
                logger.warning(
                    "Matrix: cross-signing bootstrap failed (non-fatal — clients may show 'not verified by its owner'): %s",
                    exc,
                )


async def cleanup_e2ee(client: object) -> None:
    """Close crypto database on shutdown."""
    crypto_db = getattr(client, "_myrm_crypto_db", None)
    if crypto_db and hasattr(crypto_db, "stop"):
        try:
            await crypto_db.stop()
        except Exception as exc:
            logger.debug("Matrix: could not close crypto DB: %s", exc)
