"""The export preview hides the value of a credential flag and nothing that follows it.

An unquoted value is one shell word: it ends at a separator, a closing bracket or a backtick, and a backslash keeps
the next character inside it.
"""

import pytest

from myrm_agent_harness.agent.skills.security import content_sanitizer


class TestFlagValueIsOneShellWord:
    @pytest.mark.parametrize(
        ("line", "sanitized"),
        [
            ("Run `tool --client-secret abc123xyzabc` then done.", "Run `tool --client-secret <REDACTED_VALUE>` then done."),
            ("tool --token abc123xyzabc;echo ok", "tool --token <REDACTED_VALUE>;echo ok"),
            ("x=$(tool --api-key abc123xyzabc) && next", "x=$(tool --api-key <REDACTED_VALUE>) && next"),
            ("tool --password pa\\;ssXYZ99 next", "tool --password <REDACTED_VALUE> next"),
            ("tool --password pa\\ ssXYZ99 next", "tool --password <REDACTED_VALUE> next"),
        ],
    )  # fmt: skip
    def test_only_the_value_is_replaced(self, line: str, sanitized: str) -> None:
        result = content_sanitizer.sanitize(line, "test.md")
        assert result.sanitized_content == sanitized
        assert [finding["kinds"] for finding in result.redactions] == [["cli_secret_flag"]]
        assert not result.is_safe
