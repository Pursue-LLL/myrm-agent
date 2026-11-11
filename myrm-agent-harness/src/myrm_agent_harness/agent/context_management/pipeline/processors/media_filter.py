"""Proactive media filter processor.

Strips image / video / audio content from messages before sending to the LLM
when the target model does not support multimodal input, preventing 400 errors
and wasted API calls. A model that does take media keeps the newest screenshots
only (sliding visual evidence window).

Decision logic (two sources, OR-combined):
1. Static config: ``supports_vision`` flag from LLMConfig (metadata)
2. Runtime learning: ``ModelCapabilityLearner`` records models that have
   previously rejected media at runtime (set by MEDIA_REJECTED recovery).

The window waits while the current turn's signed reasoning blocks are in flight: a block is bound to every message
before it, screenshots included, so retiring one would make the provider refuse the blocks written after it. The
user's next message ends the turn and lets the window apply; a request that would carry more than
``MAX_MEDIA_BLOCKS_HELD`` media blocks is windowed at once.

Stripping is written into the messages themselves, so media retired once stays retired in every later request.

When media is stripped, an ``agent_status`` event is emitted so the frontend
can inform the user.

[INPUT]
- base::BaseProcessor, ProcessorContext (POS: processor base class)
- core.message_origin::last_user_authored_index (POS: start of the current turn)
- core.thinking_blocks::carries_signed_blocks (POS: whether signed reasoning blocks are in flight)
- utils.image_utils (POS: image content detection & stripping)
- toolkits.llms.capability_learner (POS: runtime model capability cache)

[OUTPUT]
- MediaFilterProcessor: proactive media filter processor

[POS]
Proactive media filter processor. Strips multimodal content for text-only models and retires historical media for
the others.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from myrm_agent_harness.core.message_origin import last_user_authored_index
from myrm_agent_harness.core.thinking_blocks import carries_signed_blocks
from myrm_agent_harness.utils.image_utils import (
    content_has_media,
    count_media_items,
    strip_all_media_from_content,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ..base import BaseProcessor, ProcessorContext

logger = get_agent_logger(__name__)

CAPABILITY_REJECTS_MEDIA = "rejects_media"

# Newest messages carrying media that the window keeps, whatever their role.
RETAIN_MEDIA_MESSAGES = 2

# Anthropic applies a stricter per-image size limit to a request with more than 20 images, so past this count the
# window takes over again even while signed blocks are in flight.
MAX_MEDIA_BLOCKS_HELD = 20


def _media_held_by_signed_turn(messages: Sequence[BaseMessage]) -> bool:
    """Whether the window must wait: the turn's signed blocks are still to be replayed over its media."""
    turn = messages[last_user_authored_index(messages) + 1 :]
    if not carries_signed_blocks(turn):
        return False
    return sum(count_media_items(message.content) for message in messages) <= MAX_MEDIA_BLOCKS_HELD


class MediaFilterProcessor(BaseProcessor):
    """Proactively strip media content for models that cannot handle it.

    Positioned early in the pipeline (after ThinkingBlockCleaner) to
    prevent downstream processors from wasting effort on content that
    will be rejected by the LLM.

    The processor is a no-op when the model supports vision and has
    not previously rejected media at runtime.
    """

    @property
    def name(self) -> str:
        return "media_filter"

    async def should_process(self, context: ProcessorContext) -> bool:
        # Text-only models lose all media; vision models lose the historical media the window has left behind.
        return not self._should_skip_for_cache_preservation(context)

    async def process(self, context: ProcessorContext) -> ProcessorContext:
        stripped_count = 0

        supports_vision = context.metadata.get("supports_vision", True)
        rejects_media = False

        model_name = context.metadata.get("model_name")
        if model_name and isinstance(model_name, str):
            from myrm_agent_harness.toolkits.llms.capability_learner import (
                get_capability_learner,
            )

            learner = get_capability_learner()
            if learner.get(model_name, CAPABILITY_REJECTS_MEDIA, False):
                rejects_media = True

        strip_all = not supports_vision or rejects_media

        if not strip_all and _media_held_by_signed_turn(context.messages):
            return context

        # Determine the safe tail boundary for historical media stripping.
        # We use a Sliding Visual Evidence Window: keep the last K=2 messages that contain media,
        # regardless of role (Human, Tool, etc.). This ensures Computer Use screenshots aren't stripped.
        safe_tail_start = len(context.messages)
        if not strip_all:
            keep_media_count = RETAIN_MEDIA_MESSAGES
            for i in range(len(context.messages) - 1, -1, -1):
                content = getattr(context.messages[i], "content", None)
                if isinstance(content, list) and content_has_media(content):
                    keep_media_count -= 1
                    if keep_media_count == 0:
                        safe_tail_start = i
                        break
            if keep_media_count > 0:
                safe_tail_start = 0  # Keep all media if total media messages < K

        for i, msg in enumerate(context.messages):
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                continue

            if not content_has_media(content):
                continue

            # Strip if the model is text-only, OR if it's historical (before the safe tail boundary)
            if strip_all or i < safe_tail_start:
                new_content = strip_all_media_from_content(content)
                if new_content is not content:
                    msg.content = new_content  # type: ignore[assignment]
                    stripped_count += 1

        if stripped_count > 0:
            context.tokens_saved += stripped_count * 500  # conservative estimate per message

            if strip_all:
                logger.info(
                    "[MediaFilter] Stripped ALL media from %d message(s) for text-only model",
                    stripped_count,
                )
            else:
                logger.info(
                    "[MediaFilter] Stripped HISTORICAL media from %d message(s) to save tokens",
                    stripped_count,
                )

            runnable_config = context.metadata.get("runnable_config")
            try:
                from myrm_agent_harness.utils.event_utils import dispatch_custom_event

                await dispatch_custom_event(
                    "agent_status",
                    {
                        "step_key": "media_stripped",
                        "stripped_count": stripped_count,
                    },
                    config=runnable_config,  # type: ignore[arg-type]
                )
            except Exception as exc:
                logger.debug("Failed to dispatch media_stripped event: %s", exc)

        return context
