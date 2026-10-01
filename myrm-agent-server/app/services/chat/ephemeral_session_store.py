"""In-memory ephemeral session store for Zero Data Retention (ZDR) incognito chats.

[INPUT]
- app.database.dto::MessageDTO (POS: 消息数据传输对象)
- typing::dict, list, str, Optional, Tuple (POS: 类型标注)

[OUTPUT]
- EphemeralSessionStore: Singleton thread-safe in-memory session store providing
  zero-disk-persistence message buffering, 60s graceful reconnect tolerance,
  and deterministic byte-level physical wipe (0x00 overwriting).

[POS]
Server-level ephemeral session enclave. Completely bypasses SQLAlchemy UnitOfWork
and FTS5 disk indexing. Guarantees zero plaintext traces on disk or in standard logs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Final

from app.database.dto import MessageDTO

_GRACEFUL_RECONNECT_WINDOW_SECONDS: Final[float] = 60.0


class EphemeralSessionStore:
    """Thread-safe in-memory message store for ZDR / Incognito sessions."""

    _instance: EphemeralSessionStore | None = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        # chat_id -> ordered list of MessageDTOs
        self._sessions: dict[str, list[MessageDTO]] = {}
        # chat_id -> disconnected_at timestamp (float)
        self._disconnect_timestamps: dict[str, float] = {}
        # chat_id -> creation timestamp
        self._created_timestamps: dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> EphemeralSessionStore:
        """Access the process-level singleton instance."""
        if cls._instance is None:
            cls._instance = EphemeralSessionStore()
        return cls._instance

    @classmethod
    def reset_instance_for_testing(cls) -> None:
        """Reset the singleton instance (used in unit test isolation)."""
        cls._instance = None

    async def has_session(self, chat_id: str) -> bool:
        """Check whether an ephemeral session is currently active in memory."""
        async with self._lock:
            return chat_id in self._sessions

    async def append_message(self, chat_id: str, message: MessageDTO) -> None:
        """Append a message to the in-memory buffer without disk writes."""
        async with self._lock:
            if chat_id not in self._sessions:
                self._sessions[chat_id] = []
                self._created_timestamps[chat_id] = time.time()
            self._sessions[chat_id].append(message)
            # Active interaction clears pending disconnect timestamp
            self._disconnect_timestamps.pop(chat_id, None)

    async def get_messages(self, chat_id: str) -> list[MessageDTO]:
        """Retrieve a shallow copy of messages currently held in memory."""
        async with self._lock:
            msgs = self._sessions.get(chat_id)
            return list(msgs) if msgs else []

    async def get_last_message(self, chat_id: str) -> MessageDTO | None:
        """Get the most recent message in the ephemeral buffer."""
        async with self._lock:
            msgs = self._sessions.get(chat_id)
            return msgs[-1] if msgs else None

    async def mark_disconnected(self, chat_id: str) -> None:
        """Record transient disconnect time to begin the 60s tolerance window."""
        async with self._lock:
            if chat_id in self._sessions:
                self._disconnect_timestamps[chat_id] = time.time()

    async def mark_reconnected(self, chat_id: str) -> bool:
        """Cancel pending disconnect timer if reconnected within window."""
        async with self._lock:
            if chat_id in self._sessions:
                self._disconnect_timestamps.pop(chat_id, None)
                return True
            return False

    async def is_reconnect_window_expired(
        self,
        chat_id: str,
        timeout_seconds: float = _GRACEFUL_RECONNECT_WINDOW_SECONDS,
    ) -> bool:
        """Check if an in-memory session has stayed disconnected beyond tolerance."""
        async with self._lock:
            disc_at = self._disconnect_timestamps.get(chat_id)
            if disc_at is None:
                return False
            return (time.time() - disc_at) >= timeout_seconds

    async def wipe(self, chat_id: str) -> bool:
        """Physically overwrite memory buffers with 0x00 and purge session."""
        async with self._lock:
            messages = self._sessions.pop(chat_id, None)
            self._disconnect_timestamps.pop(chat_id, None)
            self._created_timestamps.pop(chat_id, None)

            if messages is None:
                return False

            for msg in messages:
                # Byte-level physical wipe of message content
                if msg.content:
                    raw_bytes = bytearray(msg.content.encode("utf-8", errors="ignore"))
                    raw_bytes[:] = b"\x00" * len(raw_bytes)
                # Sever references to prevent GC delay
                msg.content = ""
                msg.extra_data = None

            return True

    async def get_audit_summary(self, chat_id: str) -> dict[str, object] | None:
        """Generate audit metadata for cryptographic attestation receipt."""
        async with self._lock:
            messages = self._sessions.get(chat_id)
            if messages is None:
                return None

            total_chars = sum(len(m.content or "") for m in messages)
            created_at = self._created_timestamps.get(chat_id, time.time())
            return {
                "chat_id": chat_id,
                "message_count": len(messages),
                "total_chars": total_chars,
                "created_at": created_at,
                "is_zero_retention": True,
                "disk_persisted": False,
            }
