"""In-memory E2EE session registry (shared NaCl box per mobile client).

[INPUT]
- Client public key + handshake parameters

[OUTPUT]
- E2EE session with shared NaCl box for encrypt/decrypt

[POS]
Session registry. Maps mobile client sessions to their negotiated crypto state.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from app.remote_access.e2ee_crypto import (
    E2EECryptoError,
    decrypt_utf8,
    encrypt_utf8,
    new_session_id,
    public_key_from_b64,
)

E2EE_SESSION_TTL_SECONDS = 60 * 60
E2EE_MAX_SESSIONS = 256
E2EE_SESSION_HEADER = "X-E2EE-Session"
E2EE_PAIR_CIPHERTEXT_HEADER = "X-E2EE-Pair-Token"
E2EE_PAIR_QUERY_PARAM = "e2ee_pair"
E2EE_CONTENT_TYPE = "application/e2ee+json"


@dataclass(frozen=True, slots=True)
class E2EESession:
    session_id: str
    client_public_key: bytes
    secret_key: bytes
    expires_at: float

    def encrypt_text(self, plaintext: str) -> str:
        return encrypt_utf8(
            secret_key=self.secret_key,
            peer_public_key=self.client_public_key,
            text=plaintext,
        )

    def decrypt_text(self, bundle_b64: str) -> str:
        return decrypt_utf8(
            secret_key=self.secret_key,
            peer_public_key=self.client_public_key,
            bundle_b64=bundle_b64,
        )


class E2EESessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, E2EESession] = {}
        self._lock = asyncio.Lock()

    async def create_from_hello(
        self,
        *,
        client_public_key_b64: str,
        daemon_secret_key: bytes,
        ttl_seconds: int = E2EE_SESSION_TTL_SECONDS,
    ) -> E2EESession:
        client_public_key = public_key_from_b64(client_public_key_b64)
        session_id = new_session_id()
        session = E2EESession(
            session_id=session_id,
            client_public_key=client_public_key,
            secret_key=daemon_secret_key,
            expires_at=time.time() + ttl_seconds,
        )
        async with self._lock:
            self._prune_locked()
            if len(self._sessions) >= E2EE_MAX_SESSIONS:
                oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].expires_at)
                self._sessions.pop(oldest_id, None)
            self._sessions[session_id] = session
        return session

    async def get(self, session_id: str | None) -> E2EESession | None:
        if not session_id:
            return None
        async with self._lock:
            self._prune_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= time.time():
                self._sessions.pop(session_id, None)
                return None
            return session

    async def refresh(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions[session_id] = E2EESession(
                    session_id=session.session_id,
                    client_public_key=session.client_public_key,
                    secret_key=session.secret_key,
                    expires_at=time.time() + E2EE_SESSION_TTL_SECONDS,
                )

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [sid for sid, session in self._sessions.items() if session.expires_at <= now]
        for sid in expired:
            self._sessions.pop(sid, None)


_store = E2EESessionStore()


def get_e2ee_session_store() -> E2EESessionStore:
    return _store


def parse_encrypted_body(raw: bytes) -> str:
    """Parse ``{"v":1,"c":"<bundle>"}`` encrypted request wrapper."""
    import json

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise E2EECryptoError("Invalid encrypted JSON body") from exc
    if not isinstance(payload, dict):
        raise E2EECryptoError("Invalid encrypted JSON body")
    cipher = payload.get("c")
    if not isinstance(cipher, str) or not cipher.strip():
        raise E2EECryptoError("Missing encrypted payload")
    return cipher.strip()


__all__ = [
    "E2EE_CONTENT_TYPE",
    "E2EE_PAIR_CIPHERTEXT_HEADER",
    "E2EE_PAIR_QUERY_PARAM",
    "E2EE_SESSION_HEADER",
    "E2EE_SESSION_TTL_SECONDS",
    "E2EESession",
    "E2EESessionStore",
    "get_e2ee_session_store",
    "parse_encrypted_body",
]
