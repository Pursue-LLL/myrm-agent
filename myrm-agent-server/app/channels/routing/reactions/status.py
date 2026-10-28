"""The status reaction of one turn: a mark that the message was received, then exactly one verdict.

[INPUT]
- channels.routing.message_effects::MessageEffects (POS: best-effort reaction funnel with per-platform vocabulary negotiation)
- channels.routing.router_models::ReactionPolicy (POS: which status reactions are on and the glyphs configured for them)

[OUTPUT]
- TurnOutcome: how a turn ended (completed, failed, abandoned)
- StatusReaction: ``received`` puts the mark on the user's message beside the turn, ``finish`` takes it off and shows the verdict

[POS]
The turn (``pipeline/turn.py``) is the only owner of a message's status reaction. Owning it in one place is what
lets a turn ask the platform for one mark, one removal and one verdict, whichever way the turn ends.
"""

from __future__ import annotations

import asyncio
import enum

from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.router_models import ReactionPolicy

# What a platform shows when it rejects the configured status glyph. A failure never falls back to a
# success glyph or to a thumbs-down (a verdict on the user's message, not on the turn); when no
# candidate is accepted the status reaction is skipped.
_PROCESSING_FALLBACKS = ("\U0001f440", "\U0001f914")
_SUCCESS_FALLBACKS = ("\u2705", "\U0001f44d", "\U0001f389")
_FAILURE_FALLBACKS = ("\u274c", "\U0001f622")


class TurnOutcome(enum.Enum):
    """How a turn ended."""

    COMPLETED = "completed"
    FAILED = "failed"
    # Stopped by the user or by a shutdown: neither a success nor a failure, so no verdict is shown.
    ABANDONED = "abandoned"


class StatusReaction:
    """The reaction a turn shows on the message that started it.

    ``received`` marks the message; ``finish`` takes the mark off and shows the verdict, once: later calls do
    nothing. Every call is best-effort, a platform that refuses a reaction never reaches the turn.

    The mark is a request to the platform, which the turn does not wait for: the agent starts at once and the
    request runs beside it. ``finish`` waits for it, so the mark is never taken off before it was put on.
    """

    def __init__(
        self,
        effects: MessageEffects,
        policy: ReactionPolicy,
        channel: str,
        chat_id: str,
        message_id: str | None,
    ) -> None:
        self._effects = effects
        self._policy = policy
        self._channel = channel
        self._chat_id = chat_id
        self._message_id = message_id
        self._marked = False
        self._finished = False
        # Held here because the event loop keeps only a weak reference to a running task.
        self._mark_request: asyncio.Task[None] | None = None

    def received(self) -> None:
        """Start marking the message as received, when the policy asks for it and the platform accepts a glyph."""
        if self._marked or self._finished or not self._message_id or not self._policy.should_processing:
            return
        glyph = self._effects.accepted_reaction(self._channel, self._policy.processing_emoji, _PROCESSING_FALLBACKS)
        if glyph:
            # Set before the request: a request that is cut short may still have reached the platform.
            self._marked = True
            self._mark_request = asyncio.get_running_loop().create_task(
                self._effects.set_reaction(self._channel, self._chat_id, self._message_id, glyph)
            )

    async def marked(self) -> None:
        """Wait until the platform has answered the request that puts the mark on; how it answered does not matter."""
        if self._mark_request is not None:
            await asyncio.wait({self._mark_request})

    def cancel(self) -> None:
        """The turn is leaving: stop a mark request still in flight rather than leave it running unattended."""
        if self._mark_request is not None:
            self._mark_request.cancel()

    async def finish(self, outcome: TurnOutcome) -> None:
        """Take the mark off, then show the verdict when the policy asks for one."""
        if self._finished or not self._message_id:
            return
        self._finished = True
        await self.marked()
        if self._marked:
            await self._effects.set_reaction(self._channel, self._chat_id, self._message_id, "")
        glyph = self._verdict_glyph(outcome)
        if glyph:
            await self._effects.set_reaction(self._channel, self._chat_id, self._message_id, glyph)

    def _verdict_glyph(self, outcome: TurnOutcome) -> str:
        if not self._policy.should_completion:
            return ""
        if outcome is TurnOutcome.COMPLETED:
            return self._effects.accepted_reaction(self._channel, self._policy.completion_emoji, _SUCCESS_FALLBACKS)
        if outcome is TurnOutcome.FAILED:
            return self._effects.accepted_reaction(self._channel, self._policy.failure_emoji, _FAILURE_FALLBACKS)
        return ""
