"""Login session storage for managing async login flows.

Stores temporary session data during external channel authentication.

[INPUT]

[OUTPUT]
- LoginSessionStoreProtocol: Abstract interface for session persistence
- InMemorySessionStore: In-memory implementation (default for framework)

[POS]
Framework layer storage component. Provides out-of-the-box session management
for AsyncLoginProtocol. Sandbox deployments use InMemorySessionStore. SaaS
deployments should implement Protocol with Redis backend in control plane.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "InMemorySessionStore",
    "LoginSessionData",
    "LoginSessionStoreProtocol",
]


@dataclass
class LoginSessionData:
    """Login session metadata.

    Attributes:
        session_id: Unique session identifier
        channel_name: Channel being authenticated (e.g., "wechat")
        method: Login method (e.g., "qr_code", "oauth2")
        state_token: CSRF token for OAuth2 or session validation
        created_at: Unix timestamp when session was created
    """

    session_id: str
    channel_name: str
    method: str
    state_token: str
    created_at: float


@runtime_checkable
class LoginSessionStoreProtocol(Protocol):
    """Abstract interface for login session persistence.

    Implementations must be thread-safe and support concurrent sessions.
    Business layer can provide custom implementations (e.g., Redis for SaaS).
    """

    async def create_session(
        self,
        session_id: str,
        channel_name: str,
        method: str,
        state_token: str,
    ) -> LoginSessionData:
        """Create a new login session.

        Args:
            session_id: Unique session ID (UUIDv4 recommended)
            channel_name: Channel name
            method: Login method string
            state_token: CSRF state token

        Returns:
            LoginSessionData with created_at timestamp
        """
        ...

    async def get_session(self, session_id: str) -> LoginSessionData | None:
        """Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            LoginSessionData if found, None if expired or not exists
        """
        ...

    async def delete_session(self, session_id: str) -> bool:
        """Delete session by ID.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not exists
        """
        ...

    async def cleanup_expired(self, ttl_seconds: float) -> int:
        """Remove expired sessions older than TTL.

        Args:
            ttl_seconds: Time-to-live in seconds (e.g., 300 for 5 minutes)

        Returns:
            Number of sessions deleted
        """
        ...


class InMemorySessionStore:
    """In-memory login session store (default framework implementation).

    Suitable for Agent-in-Sandbox (local, Tauri) single-instance deployments.
    For SaaS multi-tenant deployments, implement LoginSessionStoreProtocol
    with Redis backend in control plane.

    Thread-safe using asyncio.Lock.
    """

    def __init__(self) -> None:
        """Initialize empty session store."""
        self._sessions: dict[str, LoginSessionData] = {}

    async def create_session(
        self,
        session_id: str,
        channel_name: str,
        method: str,
        state_token: str,
    ) -> LoginSessionData:
        """Create a new login session."""
        session = LoginSessionData(
            session_id=session_id,
            channel_name=channel_name,
            method=method,
            state_token=state_token,
            created_at=time.time(),
        )
        self._sessions[session_id] = session
        return session

    async def get_session(self, session_id: str) -> LoginSessionData | None:
        """Retrieve session by ID."""
        return self._sessions.get(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete session by ID."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def cleanup_expired(self, ttl_seconds: float) -> int:
        """Remove expired sessions."""
        now = time.time()
        expired_ids = [sid for sid, session in self._sessions.items() if now - session.created_at > ttl_seconds]
        for sid in expired_ids:
            del self._sessions[sid]
        return len(expired_ids)
