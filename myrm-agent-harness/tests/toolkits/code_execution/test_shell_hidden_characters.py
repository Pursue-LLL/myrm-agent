"""Layer 1 of the shell command analyzer on its own: control and invisible characters.

Kept apart from ``test_shell_command_analyzer.py``, whose module fixture skips every test when the server tree is not
checked out next to the harness; these tests need nothing outside the harness.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    ThreatLevel,
    analyze_command,
    analyze_hidden_characters,
)


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("a\x00b", "binary_injection"),
        ("a\rb", "binary_injection"),
        ("a\u200bb", "obfuscation"),
        ("a\u202eb", "obfuscation"),
    ],
)
def test_hidden_characters_block(text: str, category: str) -> None:
    threats = analyze_hidden_characters(text)
    assert [(t.level, t.category) for t in threats] == [(ThreatLevel.BLOCK, category)]


def test_clean_text_has_no_hidden_characters() -> None:
    assert analyze_hidden_characters("print('plain')\nfor x in range(3):\n    print(x)") == ()


def test_shell_syntax_is_not_judged() -> None:
    """The layer reads bytes only, so shell quoting and injection syntax are left to the shell layers."""
    assert analyze_hidden_characters("echo $'hello' $\"world\" ; `id` | sh") == ()


def test_analyze_command_reports_the_same_layer_1_threats_first() -> None:
    text = "echo a\x00b\u200b $'x'"
    hidden = analyze_hidden_characters(text)
    assert len(hidden) == 2
    assert analyze_command(text)[: len(hidden)] == hidden
