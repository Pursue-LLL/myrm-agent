"""In the JSON value a text starts with, an escaped line break reads as whitespace and comes back as it was."""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.detection.leak_detector import redact_leaks, scan_for_leaks

RANDOM_TOKEN = "aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cG"
_STAND_INS = "\x1c\x1d\x1e"


def _json_text(*lines: str) -> str:
    """A tool result as the guardrail gets it: JSON text, each line break the two characters backslash and ``n``."""
    return json.dumps({"content": "\n".join(lines), "metadata": {}})


class TestAValueStopsAtTheBreak:
    @pytest.mark.parametrize(
        ("secret_line", "next_line"),
        [
            (f"key: {RANDOM_TOKEN}", "line two here"),
            ("export OPENAI_API_KEY=abcdef0123456789abcdef", "echo done"),
            ("DB=postgres://user:s3cretpass@db.example.com:5432/app", "next line text"),
        ],
        ids=["entropy-token", "env-assignment", "database-url"],
    )
    def test_a_secret_is_masked_and_the_line_after_it_is_kept(self, secret_line: str, next_line: str) -> None:
        shown = redact_leaks(_json_text("build started", secret_line, next_line, "last line"))

        assert "[REDACTED:" in shown
        assert rf"\n{next_line}\nlast line" in shown
        assert shown.startswith('{"content": "build started\\n')

    def test_a_listing_with_no_space_in_it_is_no_secret(self) -> None:
        text = _json_text("Makefile", "hello.txt", "usage_ledger.jsonl", "---", "HELLO383506", "---", "Python 3.13.13")

        assert scan_for_leaks(text) == []
        assert redact_leaks(text) == text

    def test_a_value_labeled_as_a_credential_after_the_first_line_is_masked(self) -> None:
        shown = redact_leaks(_json_text("whoami", "DB_PASSWORD=correcthorsebatterystaple42", "done"))

        assert "correcthorsebatterystaple42" not in shown
        assert "[REDACTED:env_credential]" in shown
        assert shown.endswith(r'\ndone", "metadata": {}}')

    def test_a_scan_finds_a_secret_that_has_a_line_to_either_side(self) -> None:
        assert "high_entropy_token" in scan_for_leaks(_json_text("above", RANDOM_TOKEN, "below"))


class TestTheBreaksComeBack:
    def test_every_break_is_where_it_was_and_no_stand_in_is_left(self) -> None:
        text = _json_text("a", f"key: {RANDOM_TOKEN}", "b\tc", "d\r")

        shown = redact_leaks(text)

        assert RANDOM_TOKEN not in shown
        for escape in ("\\n", "\\r", "\\t"):
            assert shown.count(escape) == text.count(escape)
        assert not any(stand_in in shown for stand_in in _STAND_INS)

    def test_text_that_holds_a_stand_in_already_is_scanned_as_it_is(self) -> None:
        shown = redact_leaks(_json_text("a", RANDOM_TOKEN) + "\x1c trailing note")

        assert RANDOM_TOKEN not in shown
        assert shown.endswith("\x1c trailing note")

    def test_an_escaped_backslash_in_front_of_n_is_no_break(self) -> None:
        """A secret that holds a backslash and an ``n`` is one token: the JSON text has ``\\\\n`` in it."""
        secret = "aB3xK9mW2pQ7vL4nR8sT1yU6\\nhD0jF5cGz"

        shown = redact_leaks(json.dumps({"content": secret}))

        assert "hD0jF5cGz" not in shown
        assert shown.count("[REDACTED:high_entropy_token]") == 1

    def test_text_without_a_break_is_handled_as_it_is(self) -> None:
        masked = f"{RANDOM_TOKEN[:6]}***...{RANDOM_TOKEN[-4:]} [REDACTED:high_entropy_token]"

        assert redact_leaks(f"key {RANDOM_TOKEN} end") == f"key {masked} end"


class TestOnlyTheLeadingJsonValueIsRead:
    @pytest.mark.parametrize(
        "text",
        [
            'API_KEY="aB3xK9mW2pQ7\\nvL4nR8sT1yU6hD0jF5cG"',
            '[DEBUG] password: "aB3xK9mW2pQ7\\nvL4nR8sT1yU6hD0jF5cG"',
            "export DB_PASSWORD=Zx9\\tQw3Er7Ty1Ui5OpAs2Df",
        ],
        ids=["env-assignment", "text-opening-with-a-bracket", "tab-in-a-password"],
    )
    def test_a_backslash_and_an_n_in_a_secret_of_plain_text_are_no_break(self, text: str) -> None:
        shown = redact_leaks(text)

        assert scan_for_leaks(text)
        assert "vL4nR8sT1yU6hD0jF5cG" not in shown
        assert "Ty1Ui5OpAs2Df" not in shown

    def test_a_json_value_followed_by_a_note_is_read_as_json(self) -> None:
        note = "\n\n Notice: Content contains error pattern: Operation not permitted"

        shown = redact_leaks(_json_text("whoami", "DB_PASSWORD=correcthorsebatterystaple42", "done") + note)

        assert "correcthorsebatterystaple42" not in shown
        assert r'\ndone", "metadata": {}}' in shown
        assert shown.endswith(note)

    def test_the_text_after_a_json_value_is_read_as_it_is(self) -> None:
        trailing = ' api_key="aB3xK9mW2pQ7\\nvL4nR8sT1yU6hD0jF5cG"'

        shown = redact_leaks(_json_text("a", "b") + "\n\n" + trailing)

        assert "vL4nR8sT1yU6hD0jF5cG" not in shown

    def test_nested_brackets_that_are_no_json_do_not_raise(self) -> None:
        text = "[" * 200_000 + "\\n"

        assert redact_leaks(text) == text
