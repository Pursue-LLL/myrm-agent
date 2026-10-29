"""A shell command that is stored or shown loses every credential typed into it.

``redact_command_line`` is the entry of the commands the audit log and the background-job registry keep: the command
rules (``curl -u``, ``sshpass -p``, ...) run first, because their anchor is the command name and a value that touches a
separator would otherwise swallow it; the credential-named parameters follow; the shared redactor finishes. The value
of a parameter is one shell word as the shell reads it: a quoted string holds whatever is typed inside it, and outside
quotes a separator, a closing bracket or a backtick ends the word while a backslash makes the next character part of it.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.core.security.redact import redact_command_line, redact_sensitive_text
from myrm_agent_harness.core.security.redact.command_line import _KEYWORDS, _redact_named_parameters

_PASSWORD = "Secret99pwXyz"


class TestNamedParameters:
    @pytest.mark.parametrize(
        ("command", "masked", "secret"),
        [
            ("curl --token=abc123 https://api.example.com", "--token=***REDACTED***", "abc123"),
            ("cli --api-key=secret123 action", "--api-key=***REDACTED***", "secret123"),
            ("mysql --password=mypass123 -u user", "--password=***REDACTED***", "mypass123"),
            ("TOKEN=abc123 curl https://api.example.com", "TOKEN=***REDACTED***", "abc123"),
            ('curl --token="abc123" https://api.example.com', "--token=***REDACTED***", "abc123"),
            ("cli --key abc123 action", "--key=***REDACTED***", "abc123"),
        ],
    )  # fmt: skip
    def test_the_value_is_masked(self, command: str, masked: str, secret: str) -> None:
        result = _redact_named_parameters(command)
        assert masked in result
        assert secret not in result

    def test_several_parameters_are_masked(self) -> None:
        result = _redact_named_parameters("cli --api-key=key123 --token=token456 action")
        assert "--api-key=***REDACTED***" in result
        assert "--token=***REDACTED***" in result
        assert "key123" not in result
        assert "token456" not in result

    def test_names_are_matched_in_any_case(self) -> None:
        result = _redact_named_parameters("cli --TOKEN=abc123 --Password=pwd456 action")
        assert "abc123" not in result
        assert "pwd456" not in result

    @pytest.mark.parametrize("command", ["", "ls -la /tmp"])
    def test_a_command_without_a_parameter_is_unchanged(self, command: str) -> None:
        assert _redact_named_parameters(command) == command

    @pytest.mark.parametrize(
        "command",
        [
            "grep token -n README.md",
            "find . -name key -type f",
            "cat secret.txt -n 5",
            "ls -la /tmp/token_dir",
            "git log --author auth -n 3",
        ],
    )  # fmt: skip
    def test_the_word_after_a_short_option_stays_readable(self, command: str) -> None:
        """A word that follows a short option is a value of that option, not of a credential word before it."""
        assert _redact_named_parameters(command) == command


class TestCommandShapeIsKept:
    """The audit log shows the command as it was written: line breaks, indentation and spacing stay."""

    @pytest.mark.parametrize(
        "command",
        [
            "git log --oneline\ngit status",
            "cat <<'EOF' > a.py\nprint(1)\n    indented\nEOF",
            "echo  a\tb",
            "  ls -la  ",
        ],
    )  # fmt: skip
    def test_a_command_without_a_secret_is_returned_as_written(self, command: str) -> None:
        assert redact_command_line(command) == command

    def test_a_secret_is_masked_and_the_lines_around_it_are_kept(self) -> None:
        command = "export TOKEN=abc123\ncurl --api-key=key456 https://x\n  ls"
        assert _redact_named_parameters(command) == (
            "export TOKEN=***REDACTED***\ncurl --api-key=***REDACTED*** https://x\n  ls"
        )
        lines = redact_command_line(command).split("\n")
        assert len(lines) == 3
        assert "abc123" not in lines[0]
        assert "key456" not in lines[1]
        assert "https://x" in lines[1]
        assert lines[2] == "  ls"

    @pytest.mark.parametrize(
        ("command", "kept"),
        [
            ("tool --key abc123xyz;echo ok", ";echo ok"),
            ("tool --key abc123xyz|grep ok", "|grep ok"),
            ("x=$(tool --key abc123xyz) && next", ") && next"),
            ("run `tool --key abc123xyz`, then stop", "`, then stop"),
            ("tool --key abc123xyz > out.txt", "> out.txt"),
        ],
    )  # fmt: skip
    def test_the_words_after_a_value_survive(self, command: str, kept: str) -> None:
        """``--key`` is no name of the shared redactor's assignment pass, which would fold such a word into the mask."""
        result = redact_command_line(command)
        assert "abc123xyz" not in result
        assert kept in result


_SECRET_FIRST = (
    ("tool --token abc123xyz", "abc123xyz"),
    ("tool --password hunter2pw", "hunter2pw"),
    ("tool --password=hunter2pw", "hunter2pw"),
    ("tool --key abc123xyz", "abc123xyz"),
    ("tool --auth abc123xyz", "abc123xyz"),
    ("export API_TOKEN=abc123xyzabc", "abc123xyzabc"),
    ("DB_PASSWORD=hunter2pwhunter", "hunter2pwhunter"),
)
_SEPARATORS = (";", "|", "&&")
_COMMAND_SECOND = (
    f"curl -u admin:{_PASSWORD} https://x.io",
    f"sshpass -p {_PASSWORD} ssh host",
    f"docker login -u me -p {_PASSWORD} registry.io",
    f"redis-cli -a {_PASSWORD} ping",
)  # fmt: skip


class TestAValueThatTouchesASeparatorDoesNotHideTheNextCommand:
    """``tool --token abc;curl -u a:PW`` carries two secrets; swallowing ``;curl`` would leave the second one readable."""

    @pytest.mark.parametrize("second", _COMMAND_SECOND)
    @pytest.mark.parametrize("separator", _SEPARATORS)
    @pytest.mark.parametrize(("first", "first_secret"), _SECRET_FIRST)
    def test_the_entry_masks_both_secrets(self, first: str, first_secret: str, separator: str, second: str) -> None:
        result = redact_command_line(f"{first}{separator}{second}")
        assert first_secret not in result
        assert _PASSWORD not in result

    @pytest.mark.parametrize("second", _COMMAND_SECOND)
    @pytest.mark.parametrize("separator", _SEPARATORS)
    @pytest.mark.parametrize(("first", "first_secret"), _SECRET_FIRST)
    def test_the_shared_redactor_masks_the_command_after_the_value(
        self, first: str, first_secret: str, separator: str, second: str
    ) -> None:
        assert _PASSWORD not in redact_sensitive_text(f"{first}{separator}{second}")

    def test_a_word_glued_to_the_value_is_part_of_it_for_the_shared_redactor(self) -> None:
        """The shared redactor reads text of any kind: it masks to the end of the word and keeps no command word glued
        to a value; the command rules ran before it, so the credential of that command is masked all the same."""
        result = redact_sensitive_text(f"tool --client-secret abc123xyz;curl -u a:{_PASSWORD} x")
        assert result == "tool --client-secret *** -u a:*** x"

    def test_the_entry_is_idempotent(self) -> None:
        once = redact_command_line(f"tool --key abc123xyz;curl -u a:{_PASSWORD} x")
        assert once == "tool --key=***REDACTED***;curl -u a:*** x"
        assert redact_command_line(once) == once


class TestAnEscapedMetacharacterBelongsToTheValue:
    """``pa\\;ssXYZ99`` is one word in a shell: ending the value at the ``;`` would leave ``ssXYZ99`` readable."""

    @pytest.mark.parametrize("character", [";", "|", "&", "<", ">", "(", ")", "`", " "])
    def test_no_part_of_the_value_is_left(self, character: str) -> None:
        for flag in ("--password", "--key", "--auth"):
            result = redact_command_line(f"tool {flag} pa\\{character}ssXYZ99 next")
            assert "ssXYZ99" not in result
            assert "next" in result


_FIRST_HALF = "hunter2zq"
_SECOND_HALF = "Secret99zq"
_HOLDERS = (" ", "\t", "\n", ";", "|", "&", "<", ">", "(", ")", "`", "$(", " a;b | c ")


class TestAQuotedValueIsOneUnit:
    """A quoted string is one word for the shell whatever it holds, so the whole of it is the value."""

    @pytest.mark.parametrize("holder", _HOLDERS)
    @pytest.mark.parametrize("quote", ["'", '"'])
    @pytest.mark.parametrize("form", ["--{name} {value}", "--{name}={value}", "{name}={value}"])
    def test_no_part_of_a_quoted_value_is_left(self, form: str, quote: str, holder: str) -> None:
        """Every credential word, in the long-option and the assignment form, with the word after it kept."""
        for name in _KEYWORDS:
            value = f"{quote}{_FIRST_HALF}{holder}{_SECOND_HALF}{quote}"
            command = f"tool {form.format(name=name, value=value)} next"
            for result in (_redact_named_parameters(command), redact_command_line(command)):
                assert _FIRST_HALF not in result, command
                assert _SECOND_HALF not in result, command
                assert result.endswith(" next"), command

    def test_the_quotes_go_with_the_value(self) -> None:
        assert _redact_named_parameters("tool --key 'a b' next") == "tool --key=***REDACTED*** next"
        assert _redact_named_parameters('tool KEY="a;b" next') == "tool KEY=***REDACTED*** next"

    @pytest.mark.parametrize(
        "command",
        [
            f"tool --key \"{_FIRST_HALF}'{_SECOND_HALF}\" next",
            f"tool --key '{_FIRST_HALF}\"{_SECOND_HALF}' next",
            f'tool --key "{_FIRST_HALF}\\"{_SECOND_HALF}" next',
        ],
    )  # fmt: skip
    def test_the_other_quote_and_an_escaped_quote_belong_to_the_value(self, command: str) -> None:
        """The pass alone is checked: the shared redactor that follows would hide a value cut short by folding the rest
        of the word into its mask."""
        assert _redact_named_parameters(command) == "tool --key=***REDACTED*** next"

    def test_a_backslash_inside_single_quotes_is_a_character_of_the_value(self) -> None:
        """A single-quoted string ends at the next ``'`` whatever precedes it: ``'a\\'`` is one complete word."""
        assert _redact_named_parameters("tool --key 'a\\' next") == "tool --key=***REDACTED*** next"

    @pytest.mark.parametrize(
        "command",
        [
            f"tool --key {_FIRST_HALF}'x y'{_SECOND_HALF} next",
            f'tool --key "{_FIRST_HALF} x"{_SECOND_HALF} next',
            f"tool --key '{_FIRST_HALF}'\\''{_SECOND_HALF}' next",
            f"tool KEY={_FIRST_HALF}'a;b'\"c d\" next",
        ],
    )  # fmt: skip
    def test_a_word_made_of_quoted_and_unquoted_parts_is_one_value(self, command: str) -> None:
        """``'pa'\\''ss'`` is how a shell word holds a single quote: three parts, one word."""
        result = redact_command_line(command)
        assert _FIRST_HALF not in result
        assert _SECOND_HALF not in result
        assert result.endswith(" next")

    def test_a_command_after_a_quoted_value_keeps_its_own_credential_masked(self) -> None:
        result = redact_command_line(f"tool --key '{_FIRST_HALF};x' && curl -u me:{_PASSWORD} https://x.io")
        assert _FIRST_HALF not in result
        assert _PASSWORD not in result
        assert "&& curl" in result

    def test_an_unterminated_quote_is_left_as_written(self) -> None:
        """Without a closing quote there is no end to the value: the pass does not guess one."""
        command = f"tool --key '{_FIRST_HALF} {_SECOND_HALF} next"
        assert _redact_named_parameters(command) == command


class TestQuotedValuesStayLinear:
    @pytest.mark.parametrize(
        "command",
        [
            "tool --key '" + "a " * 40_000,
            "tool --key '" + "a\\'" * 30_000,
            "--key 'a " * 9_000,
        ],
        ids=["quote-never-closes", "every-quote-escaped", "many-starts"],
    )  # fmt: skip
    def test_the_entry_does_a_bounded_amount_of_work(self, command: str) -> None:
        start = time.process_time()
        redact_command_line(command)
        assert time.process_time() - start < 2.0
