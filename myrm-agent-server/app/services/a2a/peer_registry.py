"""A2A (Agent-to-Agent) Peer Registry Service.

[POS] Manages trusted remote A2A peer registries, zero-trust credential encryption,
SSRF safety validation, and AgentCard connectivity probing.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from myrm_agent_harness.toolkits.a2a.resolver import (
    A2ACardResolver,
    A2AResolveError,
    SSRFBlockedError,
)
from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.master_key import MasterKeyProvider, VaultLockedError
from app.database.connection import get_session
from app.database.dto import (
    A2APeerCreate,
    A2APeerProbeRequest,
    A2APeerProbeResponse,
    A2APeerResponse,
    A2APeerUpdate,
)
from app.database.models.a2a_peer import A2APeerModel

logger = logging.getLogger(__name__)


def _mask_token(token: str | None) -> str | None:
    """Mask credential token for safe API display."""
    if not token:
        return None
    if len(token) <= 8:
        return "********"
    return f"{token[:3]}****{token[-4:]}"


def _get_encryption_key() -> bytes:
    """Derive 256-bit encryption key from MasterKeyProvider."""
    try:
        master_key = MasterKeyProvider.get_master_key()
    except (VaultLockedError, Exception) as exc:
        logger.warning("MasterKeyProvider not unlocked, falling back to machine seed: %s", exc)
        master_key = "myrm-default-a2a-peer-vault-seed"
    return ConfigCrypto.derive_key(master_key)


def _encrypt_token(plain_token: str | None) -> str | None:
    """Encrypt plaintext token into base64 AES-256-GCM ciphertext."""
    if not plain_token:
        return None
    key = _get_encryption_key()
    return ConfigCrypto.encrypt_value({"token": plain_token}, key)


def _decrypt_token(cipher_text: str | None) -> str | None:
    """Decrypt ciphertext into plaintext token."""
    if not cipher_text:
        return None
    key = _get_encryption_key()
    try:
        data = ConfigCrypto.decrypt_value(cipher_text, key)
        return str(data.get("token", ""))
    except Exception as exc:
        logger.warning("Failed to decrypt peer token: %s", exc)
        return None


class A2APeerRegistryService:
    """Service for managing A2A trusted peers, credentials, and probe checks."""

    def __init__(self, resolver: A2ACardResolver | None = None) -> None:
        self._resolver = resolver or A2ACardResolver(timeout_seconds=15.0, cache_ttl_seconds=60.0)

    @staticmethod
    def _model_to_response(peer: A2APeerModel) -> A2APeerResponse:
        """Convert ORM model to masked response DTO."""
        has_token = bool(peer.encrypted_auth_token)
        decrypted = _decrypt_token(peer.encrypted_auth_token) if has_token else None
        masked = _mask_token(decrypted)

        return A2APeerResponse(
            id=peer.id,
            name=peer.name,
            base_url=peer.base_url,
            description=peer.description,
            auth_type=peer.auth_type,
            is_active=peer.is_active,
            has_token=has_token,
            masked_token=masked,
            last_probed_at=peer.last_probed_at,
            last_probe_status=peer.last_probe_status,
            last_probe_error=peer.last_probe_error,
            cached_card_json=peer.cached_card_json,
            created_at=peer.created_at,
            updated_at=peer.updated_at,
        )

    async def list_peers(self, *, only_active: bool = False) -> list[A2APeerResponse]:
        """List all registered A2A peers."""
        async with get_session() as session:
            stmt = select(A2APeerModel).order_by(A2APeerModel.created_at.desc())
            if only_active:
                stmt = stmt.where(A2APeerModel.is_active.is_(True))
            result = await session.execute(stmt)
            peers = result.scalars().all()
            return [self._model_to_response(p) for p in peers]

    async def get_peer(self, peer_id: str) -> A2APeerResponse | None:
        """Get a single A2A peer by ID."""
        async with get_session() as session:
            peer = await session.get(A2APeerModel, peer_id)
            if not peer:
                return None
            return self._model_to_response(peer)

    async def get_peer_credentials(self, peer_id: str) -> tuple[str, str, str | None] | None:
        """Internal lookup: returns (base_url, auth_type, decrypted_token)."""
        async with get_session() as session:
            peer = await session.get(A2APeerModel, peer_id)
            if not peer or not peer.is_active:
                return None
            token = _decrypt_token(peer.encrypted_auth_token) if peer.encrypted_auth_token else None
            return (peer.base_url, peer.auth_type, token)

    async def create_peer(self, data: A2APeerCreate) -> A2APeerResponse:
        """Register a new trusted A2A peer."""
        encrypted_token = _encrypt_token(data.auth_token) if data.auth_token else None
        peer_id = str(uuid.uuid4())

        async with get_session() as session:
            peer = A2APeerModel(
                id=peer_id,
                name=data.name.strip(),
                base_url=data.base_url.strip().rstrip("/"),
                description=data.description.strip() if data.description else None,
                auth_type=data.auth_type,
                encrypted_auth_token=encrypted_token,
                is_active=data.is_active,
            )
            session.add(peer)
            await session.commit()
            await session.refresh(peer)
            logger.info("Registered new A2A peer: id=%s name=%s url=%s", peer.id, peer.name, peer.base_url)
            return self._model_to_response(peer)

    async def update_peer(self, peer_id: str, data: A2APeerUpdate) -> A2APeerResponse | None:
        """Update an existing A2A peer."""
        async with get_session() as session:
            peer = await session.get(A2APeerModel, peer_id)
            if not peer:
                return None

            if data.name is not None:
                peer.name = data.name.strip()
            if data.base_url is not None:
                peer.base_url = data.base_url.strip().rstrip("/")
            if data.description is not None:
                peer.description = data.description.strip() if data.description else None
            if data.auth_type is not None:
                peer.auth_type = data.auth_type
            if data.is_active is not None:
                peer.is_active = data.is_active
            if data.auth_token is not None:
                peer.encrypted_auth_token = _encrypt_token(data.auth_token) if data.auth_token else None

            await session.commit()
            await session.refresh(peer)
            logger.info("Updated A2A peer: id=%s name=%s", peer.id, peer.name)
            return self._model_to_response(peer)

    async def delete_peer(self, peer_id: str) -> bool:
        """Delete an A2A peer by ID."""
        async with get_session() as session:
            peer = await session.get(A2APeerModel, peer_id)
            if not peer:
                return False
            await session.delete(peer)
            await session.commit()
            logger.info("Deleted A2A peer: id=%s", peer_id)
            return True

    async def probe(self, request: A2APeerProbeRequest) -> A2APeerProbeResponse:
        """Probe connectivity to a remote A2A peer and fetch its AgentCard metadata."""
        target_url = request.url
        auth_token = request.auth_token
        auth_type = "bearer"
        peer_to_update: A2APeerModel | None = None
        db_session: AsyncSession | None = None

        if request.peer_id:
            db_session = get_session()
            session = await db_session.__aenter__()
            peer_to_update = await session.get(A2APeerModel, request.peer_id)
            if peer_to_update:
                target_url = peer_to_update.base_url
                auth_type = peer_to_update.auth_type
                if not auth_token and peer_to_update.encrypted_auth_token:
                    auth_token = _decrypt_token(peer_to_update.encrypted_auth_token)

        if not target_url:
            if db_session:
                await db_session.__aexit__(None, None, None)
            return A2APeerProbeResponse(
                success=False,
                status="error",
                error="Target URL or valid peer_id is required for probe",
            )

        headers: dict[str, str] = {}
        if auth_token:
            if auth_type == "bearer":
                headers["Authorization"] = f"Bearer {auth_token}"
            elif auth_type == "api_key":
                headers["X-API-Key"] = auth_token

        start_time = time.monotonic()
        try:
            card = await self._resolver.resolve(target_url, headers=headers)
            latency_ms = round((time.monotonic() - start_time) * 1000, 2)
            card_dict = card.model_dump(mode="json")

            if peer_to_update and db_session:
                peer_to_update.last_probed_at = datetime.now()
                peer_to_update.last_probe_status = "ok"
                peer_to_update.last_probe_error = None
                peer_to_update.cached_card_json = card_dict
                await db_session.commit()

            return A2APeerProbeResponse(
                success=True,
                status="ok",
                latency_ms=latency_ms,
                agent_card=card_dict,
            )
        except SSRFBlockedError as exc:
            latency_ms = round((time.monotonic() - start_time) * 1000, 2)
            err_msg = f"SSRF Blocked: {exc}"
            if peer_to_update and db_session:
                peer_to_update.last_probed_at = datetime.now()
                peer_to_update.last_probe_status = "ssrf_blocked"
                peer_to_update.last_probe_error = err_msg
                await db_session.commit()
            return A2APeerProbeResponse(
                success=False,
                status="ssrf_blocked",
                latency_ms=latency_ms,
                error=err_msg,
            )
        except (A2AResolveError, Exception) as exc:
            latency_ms = round((time.monotonic() - start_time) * 1000, 2)
            err_msg = str(exc)
            if peer_to_update and db_session:
                peer_to_update.last_probed_at = datetime.now()
                peer_to_update.last_probe_status = "error"
                peer_to_update.last_probe_error = err_msg
                await db_session.commit()
            return A2APeerProbeResponse(
                success=False,
                status="error",
                latency_ms=latency_ms,
                error=err_msg,
            )
        finally:
            if db_session:
                await db_session.__aexit__(None, None, None)


_peer_registry_service: A2APeerRegistryService | None = None


def get_a2a_peer_registry() -> A2APeerRegistryService:
    """Singleton provider for A2APeerRegistryService."""
    global _peer_registry_service
    if _peer_registry_service is None:
        _peer_registry_service = A2APeerRegistryService()
    return _peer_registry_service
