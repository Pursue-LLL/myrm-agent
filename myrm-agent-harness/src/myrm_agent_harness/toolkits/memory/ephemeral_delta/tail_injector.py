"""Appends per-turn blocks (ephemeral session deltas, knowledge pack) to the tail of the final HumanMessage.

[INPUT]
- toolkits.memory.ephemeral_delta.models::EphemeralDeltaItem (POS: Types and models for ephemeral delta.)
- Third-party: langchain_core

[OUTPUT]
- append_block_to_last_human: Returns the messages with a text block appended to the final HumanMessage; the history before it stays byte-identical.
- HumanTailDeltaInjector: Injects active ephemeral session deltas at the tail of the final HumanMessage.

[POS]
Tail-of-turn injection primitive: per-turn content lives only on the final HumanMessage so the SystemMessage and earlier history keep their prompt-cache prefix.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Sequence
from typing import cast

from langchain_core.messages import AnyMessage, HumanMessage

from myrm_agent_harness.toolkits.memory.ephemeral_delta.models import (
    EphemeralDeltaItem,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DELTA_CHARS = 1500


def append_block_to_last_human(messages: Sequence[AnyMessage], block: str) -> list[AnyMessage]:
    """Return ``messages`` with ``block`` appended to the tail of the final HumanMessage.

    The input sequence and its messages are never mutated. Multimodal content keeps
    every original part untouched and gains one trailing text part. Without a block or
    a HumanMessage the result is an unmodified copy.
    """
    out_messages = list(messages)
    if not block:
        return out_messages

    target_idx = next(
        (i for i in range(len(out_messages) - 1, -1, -1) if isinstance(out_messages[i], HumanMessage)),
        -1,
    )
    if target_idx == -1:
        logger.debug("No HumanMessage found in request messages; skipping tail injection")
        return out_messages

    original_human = cast(HumanMessage, out_messages[target_idx])
    content = original_human.content
    new_content: str | list[str | dict[str, object]]
    if isinstance(content, str):
        new_content = f"{content}\n\n{block}" if content else block
    else:
        new_content = [*content, {"type": "text", "text": f"\n\n{block}"}]
    out_messages[target_idx] = HumanMessage(
        content=new_content,
        additional_kwargs=dict(original_human.additional_kwargs),
        id=original_human.id,
        name=original_human.name,
    )
    return out_messages


class HumanTailDeltaInjector:
    """Injects active ephemeral session deltas at the tail of the final HumanMessage.

    Layout invariant:
    1. SystemMessage and prior history bytes are not modified.
    2. Deltas attach only to the final HumanMessage tail.
    3. Provider cache hit rate is observed elsewhere (chat health / usage), not inferred here.
    """

    def __init__(self, max_delta_chars: int = _DEFAULT_MAX_DELTA_CHARS) -> None:
        self.max_delta_chars = max_delta_chars

    def format_deltas_block(
        self,
        deltas: Sequence[EphemeralDeltaItem],
    ) -> str:
        """Format deltas into a compact, sanitized XML tag block."""
        if not deltas:
            return ""

        lines: list[str] = [
            "<ephemeral_session_deltas>",
            "  <precedence>When a delta conflicts with stable user memory or earlier chat turns, follow the delta. "
            "Agent instructions and mandatory veto rules still take precedence.</precedence>",
        ]

        total_chars = 0
        for item in deltas:
            escaped_key = html.escape(item.target_key)
            escaped_action = html.escape(item.action.value)
            escaped_id = html.escape(item.delta_id)
            escaped_content = html.escape(item.content.strip())

            delta_line = (
                f'  <delta id="{escaped_id}" key="{escaped_key}" action="{escaped_action}">{escaped_content}</delta>'
            )

            # Enforce budget guard
            if total_chars + len(delta_line) > self.max_delta_chars:
                lines.append("  <!-- Remaining deltas truncated due to budget constraints -->")
                break

            lines.append(delta_line)
            total_chars += len(delta_line)

        lines.append("</ephemeral_session_deltas>")
        return "\n".join(lines)

    def inject_deltas(
        self,
        messages: Sequence[AnyMessage],
        deltas: Sequence[EphemeralDeltaItem],
    ) -> list[AnyMessage]:
        """Attach active deltas to the tail of the last HumanMessage in the sequence.

        If no active deltas or no HumanMessage exists, returns the original sequence untouched.
        """
        if not deltas:
            return list(messages)
        return append_block_to_last_human(messages, self.format_deltas_block(deltas))
