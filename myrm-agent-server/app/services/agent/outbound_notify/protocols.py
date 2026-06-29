"""Outbound notification sender protocol.

[INPUT]
- .types::NotifyResult, NotifyTarget (POS: outbound notification data types)

[OUTPUT]
- NotificationSender: Protocol for channel outbound delivery.

[POS]
Server-side contract for agent-initiated outbound notifications.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import NotifyResult, NotifyTarget


@runtime_checkable
class NotificationSender(Protocol):
    """Delivers outbound notifications to configured external channels."""

    async def send(
        self,
        target: NotifyTarget,
        body: str,
    ) -> NotifyResult:
        """Deliver a notification to the specified target."""
        ...

    async def list_available_targets(self) -> list[NotifyTarget]:
        """Return configured notification targets."""
        ...
