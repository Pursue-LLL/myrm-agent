"""Advisor side-thread message store (ephemeral, per parent chat).

[INPUT]
Parent chat_id + user/assistant messages.

[OUTPUT]
Ordered message history for advisor thread rendering.

[POS]
In-memory thread storage; cleared on server restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class AdvisorMessage:
    id: str
    role: str
    content: str
    tier: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "tier": self.tier,
            "created_at": self.created_at,
        }


class AdvisorThreadStore:
    _threads: dict[str, list[AdvisorMessage]] = {}

    @classmethod
    def append(
        cls,
        parent_chat_id: str,
        *,
        role: str,
        content: str,
        tier: str = "tier0",
    ) -> AdvisorMessage:
        msg = AdvisorMessage(
            id=str(uuid4()),
            role=role,
            content=content,
            tier=tier,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        bucket = cls._threads.setdefault(parent_chat_id, [])
        bucket.append(msg)
        if len(bucket) > 50:
            del bucket[:-50]
        return msg

    @classmethod
    def list_messages(cls, parent_chat_id: str) -> list[AdvisorMessage]:
        return list(cls._threads.get(parent_chat_id, ()))

    @classmethod
    def clear(cls, parent_chat_id: str) -> None:
        cls._threads.pop(parent_chat_id, None)


__all__ = ["AdvisorMessage", "AdvisorThreadStore"]
