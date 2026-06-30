"""Outbound notification sender protocol.

[INPUT]
- .types::NotifyResult, NotifyTarget (POS: outbound notification data types)
- app.channels.types.messages::MediaAttachment (POS: media attachment model)

[OUTPUT]
- NotificationSender: Protocol for channel outbound delivery.

[POS]
Server-side contract for agent-initiated outbound notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .types import NotifyResult, NotifyTarget

if TYPE_CHECKING:
    from app.channels.types.messages import MediaAttachment


@runtime_checkable
class NotificationSender(Protocol):
    """Delivers outbound notifications to configured external channels."""

    async def send(
        self,
        target: NotifyTarget,
        body: str,
        media: tuple[MediaAttachment, ...] = (),
    ) -> NotifyResult:
        """Deliver a notification to the specified target."""
        ...

    async def list_available_targets(self) -> list[NotifyTarget]:
        """Return configured notification targets."""
        ...
