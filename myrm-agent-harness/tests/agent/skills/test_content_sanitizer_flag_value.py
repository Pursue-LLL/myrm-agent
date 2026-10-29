"""The export preview hides the value of a credential flag up to the next whitespace and nothing that follows it.

A backslash keeps the next character inside the value, a space included. A closing backtick that touches the value is
part of it: the value of an unquoted flag is whatever is not whitespace or a quote.
"""

import pytest

from myrm_agent_harness.agent.skills.security import content_sanitizer


class TestFlagValueRunsToTheEndOfTheWord:
    @pytest.mark.parametrize(
        ("line", "sanitized"),
        [
            ("Run `tool --client-secret abc123xyzabc` then done.", "Run `tool --client-secret <REDACTED_VALUE> then done."),
            ("tool --token abc123xyz;MIDSECRET next", "tool --token <REDACTED_VALUE> next"),
            ("tool --api-key abc123xyz&MIDSECRET next", "tool --api-key <REDACTED_VALUE> next"),
            ("tool --password pa\\;ssXYZ99 next", "tool --password <REDACTED_VALUE> next"),
            ("tool --password pa\\ ssXYZ99 next", "tool --password <REDACTED_VALUE> next"),
        ],
    )  # fmt: skip
    def test_the_value_is_replaced_to_the_end_of_the_word(self, line: str, sanitized: str) -> None:
        result = content_sanitizer.sanitize(line, "test.md")
        assert result.sanitized_content == sanitized
        assert [finding["kinds"] for finding in result.redactions] == [["cli_secret_flag"]]
        assert not result.is_safe
