"""Reasoning Anchor Pipeline Processor.

Extracts decision anchors from thinking streams before ThinkingBlockCleaner
strips them, and injects preserved decision anchors into the latest user message
without disrupting Prompt Prefix Cache.

[INPUT]
- core.message_origin::is_user_authored_human_message (POS: Message-provenance primitives shared by the approval, security, memory-context and context-management layers.)
- pipeline.base::BaseProcessor, ProcessorContext (POS: Pipeline processor base class)
- strategies.reasoning.anchor_extractor::extract_raw_reasoning, extract_reasoning_anchors (POS: Extraction logic)
- strategies.reasoning.anchor_ledger::get_session_anchor_ledger (POS: Session anchor ledger)
- utils.logger_utils::get_agent_logger (POS: Agent logger)

[OUTPUT]
- ReasoningAnchorProcessor: Pipeline processor for reasoning preservation

[POS]
Positioned at the front of the default pipeline, immediately before ThinkingBlockCleaner.
The injected block is frozen per user turn: in a tool loop the latest user message is the
first message of the request, so rewriting it between rounds would invalidate the cached
prefix of the whole conversation behind it.
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage

from myrm_agent_harness.core.message_origin import is_user_authored_human_message
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ...strategies.reasoning.anchor_extractor import extract_raw_reasoning, extract_reasoning_anchors
from ...strategies.reasoning.anchor_ledger import get_session_anchor_ledger
from ..base import BaseProcessor, ProcessorContext

logger = get_agent_logger(__name__)

_ANCHOR_BLOCK_PREFIX = "[PRESERVED REASONING ANCHORS & CONSTRAINTS]"
_ANCHOR_BLOCK_REGEX = re.compile(
    r"\n\n\[PRESERVED REASONING ANCHORS & CONSTRAINTS\].*?(?=\n\n|\Z)",
    re.DOTALL,
)


def _precedes_tool_call(msg: AIMessage) -> bool:
    """Whether the message's reasoning leads into a tool call rather than ending the turn."""
    return bool(msg.tool_calls or msg.additional_kwargs.get("tool_calls"))


def _with_anchor_block(content: str | list[str | dict[str, object]], block: str) -> str | list[str | dict[str, object]]:
    """Return ``content`` carrying exactly one anchor block, dropping any earlier one."""
    if isinstance(content, str):
        return f"{_ANCHOR_BLOCK_REGEX.sub('', content).rstrip()}\n\n{block}"
    kept: list[str | dict[str, object]] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = _ANCHOR_BLOCK_REGEX.sub("", str(item.get("text", ""))).rstrip()
            if text and not text.startswith(_ANCHOR_BLOCK_PREFIX):
                kept.append({"type": "text", "text": text})
        else:
            kept.append(item)
    kept.append({"type": "text", "text": block})
    return kept


class ReasoningAnchorProcessor(BaseProcessor):
    """Reasoning Anchor Processor.

    1. Scans messages for reasoning content and extracts core decision anchors
       into the session's immutable ledger before ThinkingBlockCleaner strips raw thoughts.
    2. Injects the anchors known at the start of the turn into the user's latest message.
       Anchors recorded while the turn runs appear from the next turn on, so the message
       stays byte-identical across tool rounds and the Prompt Prefix Cache keeps matching.
    """

    def __init__(self, *, max_anchors: int = 10) -> None:
        self._max_anchors = max_anchors

    @property
    def name(self) -> str:
        return "ReasoningAnchorProcessor"

    async def should_process(self, context: ProcessorContext) -> bool:
        """Process whenever messages are present to ensure anchors are tracked and injected."""
        return bool(context.messages)

    async def process(self, context: ProcessorContext) -> ProcessorContext:
        session_id = context.chat_id or "default_session"
        ledger = get_session_anchor_ledger(session_id, max_anchors=self._max_anchors)

        # Step 1: Scan AIMessages to extract new decision anchors before stripping
        extracted_count = 0
        last_human_idx = -1
        human_count = 0
        for idx, msg in enumerate(context.messages):
            # A notice the runtime appended behind the user's message is not a turn of its own.
            if is_user_authored_human_message(msg):
                last_human_idx = idx
                human_count += 1
            elif isinstance(msg, AIMessage):
                raw_reasoning = extract_raw_reasoning(msg)
                if raw_reasoning:
                    anchors = extract_reasoning_anchors(
                        raw_reasoning,
                        turn_index=idx,
                        tail_fallback=not _precedes_tool_call(msg),
                    )
                    if anchors:
                        ledger.record_anchors(anchors)
                        extracted_count += len(anchors)

        active_anchors = ledger.get_anchors()
        context.metadata["active_reasoning_anchors"] = [
            {
                "id": a.anchor_id,
                "turn": a.turn_index,
                "category": a.category,
                "content": a.content,
            }
            for a in active_anchors
        ]

        if extracted_count > 0:
            logger.info(
                "[ReasoningAnchor] Extracted %d new anchors, active total=%d (session=%s)",
                extracted_count,
                len(active_anchors),
                session_id,
            )

        if last_human_idx == -1:
            return context

        # Step 2: Inject the block frozen for this turn into the user's latest message
        human_msg = context.messages[last_human_idx]
        block = ledger.render_for_turn(f"{human_count}:{human_msg.id or id(human_msg)}")
        if not block:
            return context

        updated = _with_anchor_block(human_msg.content, block)
        if updated != human_msg.content:
            human_msg.content = updated
        return context
