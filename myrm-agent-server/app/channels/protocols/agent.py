"""Agent executor protocol — processes inbound messages through the Agent pipeline.

Business layer provides a concrete implementation that creates and runs
an Agent with the user's configuration.

[INPUT]
- channels.types::InboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- utils.cancellation::CancellationToken (POS: Agent  ContextVar  BaseAgent)

[OUTPUT]
- AgentExecutor: Agent execution protocol (streaming AsyncGenerator, supports cancel token)

[POS]
Agent execution protocol for Channel inbound messages. Framework AgentRouter delegates
inbound messages to business-layer Agents via this protocol. execute_stream returns
AsyncGenerator yielding ProgressUpdate (progress) and OutboundMessage (final result).
External cancellation (e.g. user /stop command)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.channels.types import (
        InboundMessage,
        OutboundMessage,
        ProgressUpdate,
        FissionTopologyUpdate,
        TopicContext,
    )


@runtime_checkable
class AgentExecutor(Protocol):
    """Protocol for executing agent tasks from inbound channel messages.

    Implemented by the business layer (e.g. using AgentFactory).
    The executor is responsible for:
    1. Loading the user's default agent configuration
    2. Creating an Agent instance
    3. Streaming progress updates during execution
    4. Yielding the final OutboundMessage as the last event
    """

    def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str,
        *,
        cancel_token: CancellationToken | None = None,
        steering_token: SteeringToken | None = None,
        topic_context: TopicContext | None = None,
    ) -> AsyncGenerator[ProgressUpdate | FissionTopologyUpdate | OutboundMessage]:
        """Stream agent execution progress and final result.

        Args:
            msg: Inbound channel message to process.
            user_id: Resolved system user ID.
            cancel_token: Optional cancellation token for cooperative cancellation
                (e.g. user /stop command). Implementations should forward this to
                BaseAgent.run() or periodically check ``cancel_token.is_cancelled``.
            steering_token: Optional steering token allowing mid-execution direction
                changes (e.g. user /steer command). Implementations should forward
                this to the Agent's process_stream for runtime message injection.
            topic_context: Optional per-topic overrides (agent_id, enabled state)
                for forum-style thread routing.

        Yields:
            ProgressUpdate — zero or more progress labels during execution.
            OutboundMessage — exactly one, as the final yielded value.
        """
        ...
