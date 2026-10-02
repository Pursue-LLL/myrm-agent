"""R2: observed-context block must carry the anti-injection behavioral declaration.

The declaration tells the LLM that context-block messages were merely observed
and are not necessarily addressed to it — only the post-separator trigger line
is a directed request. It is a fixed constant (prompt-cache stability, no
implementation detail leakage).
"""

from __future__ import annotations

from app.channels.types import ContextEntry
from app.core.channel_bridge.agent_executor.helpers import _format_group_context_section


def _entry(sender: str, content: str) -> ContextEntry:
    return ContextEntry(sender_id=sender, content=content, timestamp=0.0, sender_name=sender)


class TestObservedContextDeclaration:
    def test_declaration_rendered_under_header(self) -> None:
        out = _format_group_context_section((_entry("Alice", "lunch at noon?"),), "Bob: status?")
        assert out.startswith("[Recent group chat messages for context]\n")
        assert "not necessarily" in out
        assert "after the separator" in out
        assert "Alice: lunch at noon?" in out
        assert out.endswith("---\nBob: status?")

    def test_no_context_block_without_entries(self) -> None:
        out = _format_group_context_section((), "Bob: status?")
        assert out == "Bob: status?"

    def test_declaration_is_fixed_constant_across_renders(self) -> None:
        first = _format_group_context_section((_entry("A", "1"),), "trigger-a")
        second = _format_group_context_section((_entry("B", "2"),), "trigger-b")
        # Line 1 (right under the header) must be byte-identical every render
        assert first.splitlines()[1] == second.splitlines()[1]

    def test_blank_entries_skip_declaration_since_block_empty(self) -> None:
        out = _format_group_context_section((_entry("A", "   "),), "Bob: go")
        assert out == "Bob: go"