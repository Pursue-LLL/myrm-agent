"""Pairing protocol — maps external channel identities to system users.

Business layer provides a concrete implementation backed by its database.

[INPUT]
(No external dependencies, pure protocol definitions)

[OUTPUT]
- PairingStore: User identity pairing storage protocol
- PairingStatus: Pairing status enum

[POS]
Storage protocol for Channel user identity binding. Framework resolves inbound
message sender identity via this protocol; business layer provides DB implementation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.channels.types import ReactionLevel


class PairingStatus(StrEnum):
    """Status of a channel-user pairing."""

    ACTIVE = "active"
    PENDING = "pending"
    BLOCKED = "blocked"


class DmPolicy(StrEnum):
    """DM access policy for inbound channel messages."""

    DISABLED = "disabled"
    OPEN = "open"
    ALLOWLIST = "allowlist"
    PAIRING = "pairing"


class GroupPolicy(StrEnum):
    """Group chat access policy for inbound channel messages.

    Unlike DmPolicy, groups don't support 'pairing' — the bot is already
    in the group, so identity binding is unnecessary.
    """

    DISABLED = "disabled"
    OPEN = "open"
    ALLOWLIST = "allowlist"


class GroupTriggerMode(StrEnum):
    """How the bot decides whether to respond in a group chat."""

    MENTION_ONLY = "mention_only"
    PREFIX = "prefix"
    ALL = "all"


@runtime_checkable
class PairingStore(Protocol):
    """Storage protocol for channel-user identity mapping.

    Implemented by the business layer (e.g. SQLAlchemy-backed store).
    """

    async def resolve(self, channel: str, sender_id: str) -> str | None:
        """Resolve a channel-specific sender to a system user_id.

        Returns None if no active pairing exists.
        """
        ...

    async def touch_display_name(self, channel: str, sender_id: str, display_name: str) -> None:
        """Update display_name only if it differs from the stored value.

        Called on every resolved message so the pairing list stays current.
        Implementations should use a conditional UPDATE to avoid unnecessary writes.
        """
        ...

    async def bind(
        self,
        channel: str,
        sender_id: str,
        user_id: str,
        *,
        status: PairingStatus = PairingStatus.ACTIVE,
        display_name: str | None = None,
    ) -> None:
        """Create or update a pairing between a channel identity and a system user."""
        ...

    async def unbind(self, channel: str, sender_id: str) -> None:
        """Remove a pairing."""
        ...

    async def get_status(self, channel: str, sender_id: str) -> PairingStatus | None:
        """Get the pairing status for a channel identity.

        Returns None if no pairing exists.
        """
        ...


@runtime_checkable
class ChannelPolicyProvider(Protocol):
    """Provides DM and group access policies for the AgentRouter.

    Implemented by the business layer to read policy from user configuration.
    Resolution order: channel-specific override > global default.
    """

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        """Get the effective DM policy for a channel."""
        ...

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        """Get the effective group chat policy for a channel."""
        ...

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        """Get the group trigger mode and prefixes for a channel.

        Returns (mode, prefixes). Prefixes are only used when mode is PREFIX.
        Default: (MENTION_ONLY, []).
        """
        ...

    async def get_reaction_level(self, channel: str) -> ReactionLevel:
        """Get the effective reaction level for a channel.

        Default: SIMPLE (react / only on completion/failure).
        """
        ...

    async def get_enabled_groups(self) -> set[str]:
        """Get the set of explicitly enabled group JIDs (explicit opt-in).

        Empty set means no groups are enabled — the bot will not respond in any group.
        """
        ...

    async def get_guest_mode(self, channel: str) -> bool:
        """Whether non-enabled groups may trigger a one-shot @mention guest turn."""
        ...

    async def get_free_response_chats(self, channel: str) -> set[str]:
        """Get the set of explicitly whitelisted group JIDs for free response (no mention required).

        Empty set means no groups are whitelisted.
        """
        ...

    async def get_default_user_id(self) -> str | None:
        """Get the default user_id (e.g. local single-user mode)."""
        ...
