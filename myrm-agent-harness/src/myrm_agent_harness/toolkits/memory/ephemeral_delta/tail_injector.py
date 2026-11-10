"""Appends the active ephemeral session deltas to the tail of the user's latest message.

[INPUT]
- core.message_tail::append_block_to_last_user_message (POS: Tail-of-turn injection primitive: per-turn content lives only on the user's latest message so the SystemMessage and earlier history keep their prompt-cache prefix.)
- toolkits.memory.ephemeral_delta.models::EphemeralDeltaItem (POS: Types and models for ephemeral delta.)
- Third-party: langchain_core

[OUTPUT]
- HumanTailDeltaInjector: Injects active ephemeral session deltas at the tail of the user's latest message.

[POS]
Delta renderer of the tail-of-turn injection: per-turn content lives only on the user's latest message so the SystemMessage and earlier history keep their prompt-cache prefix.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from langchain_core.messages import AnyMessage

from myrm_agent_harness.core.message_tail import append_block_to_last_user_message
from myrm_agent_harness.toolkits.memory.ephemeral_delta.models import (
    EphemeralDeltaItem,
)

_DEFAULT_MAX_DELTA_CHARS = 1500


class HumanTailDeltaInjector:
    """Injects active ephemeral session deltas at the tail of the user's latest message.

    Layout invariant:
    1. SystemMessage and prior history bytes are not modified.
    2. Deltas attach only to the tail of the user's latest message.
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
        """Attach active deltas to the tail of the user's latest message in the sequence.

        If no active deltas or no user message exists, returns the original sequence untouched.
        """
        if not deltas:
            return list(messages)
        return append_block_to_last_user_message(messages, self.format_deltas_block(deltas))
