"""Topic management protocol — resolve, bind, and unbind per-topic configuration.

Business layer provides a concrete implementation that reads/writes per-topic
configuration from the user's settings (e.g. UserConfig table).

[INPUT]
- channels.types::TopicContext (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- TopicManager: Protocol for resolving, binding, unbinding, and syncing metadata for topic overrides

[POS]
Topic/channel-level management protocol. Supports two binding granularities for flexible channel routing.

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.channels.types import TopicContext


@runtime_checkable
class TopicManager(Protocol):
    """Protocol for managing per-topic/channel configuration.

    Supports resolving existing bindings, creating new bindings,
    and removing bindings. Works at two granularity levels:
    - thread_id provided: per-topic binding (forum threads)
    - thread_id is None: per-channel binding (entire chat)
    """

    async def resolve_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
    ) -> TopicContext | None:
        """Resolve per-topic or per-channel configuration.

        Returns TopicContext with overrides, or None for default behavior.
        When thread_id is None, resolves channel-level binding.
        """
        ...

    async def bind_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
        *,
        agent_id: str | None = None,
    ) -> TopicContext:
        """Create or update a topic or channel binding.

        When thread_id is None, creates a channel-level binding.
        Persists the binding to storage and returns the new TopicContext.
        """
        ...

    async def sync_topic_metadata(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        """Synchronize topic metadata (e.g., from incoming messages).

        This should update the display name and avatar URL if the topic exists,
        or create a new topic entry without an agent binding if it doesn't.
        """
        ...

    async def unbind_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
    ) -> bool:
        """Remove a topic or channel binding.

        Returns True if a binding was removed, False if none existed.
        """
        ...
