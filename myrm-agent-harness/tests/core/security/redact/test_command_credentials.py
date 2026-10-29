"""A password or a cookie typed as a command-line argument is masked, in the four forms no name-based rule sees.

``curl -u user:pass``, ``curl -b 'sid=…'``, ``sshpass -p pass`` and ``mysql -ppass`` carry the credential in a short
option whose name says nothing, so each rule is anchored on the command name and stays inside one command. Everything
that merely looks alike (``ssh -p 22``, ``git push -u``, ``-u admin:$PASSWORD``, a cookie jar file) is left readable.
"""

from __future__ import annotations

import json
import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_PASSWORD = "s3cretPw99"
_COOKIES = "sid=abcDEF123456; theme=dark"


def _masked(text: str, *, source_code: bool = False) -> str:
    return redact_sensitive_text(text, source_code=source_code)


class TestCurlUser:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"curl -u admin:{_PASSWORD} https://api.example.com/v1", "curl -u admin:*** https://api.example.com/v1"),
            (f"curl --user admin:{_PASSWORD} https://x", "curl --user admin:*** https://x"),
            (f"curl --user=admin:{_PASSWORD} https://x", "curl --user=admin:*** https://x"),
            (f"curl -uadmin:{_PASSWORD} https://x", "curl -uadmin:*** https://x"),
            (f"curl -sS -u admin:{_PASSWORD} -o out.json https://x", "curl -sS -u admin:*** -o out.json https://x"),
            (f"curl https://x/api -u admin:{_PASSWORD} -H 'A: b'", "curl https://x/api -u admin:*** -H 'A: b'"),
            (f"curl 'https://x/a?b=1&c=2' -u admin:{_PASSWORD}", "curl 'https://x/a?b=1&c=2' -u admin:***"),
            ("curl -u 'admin:p ass w0rd' https://x", "curl -u 'admin:***' https://x"),
            (f'curl -u "admin:{_PASSWORD}" https://x', 'curl -u "admin:***" https://x'),
            (f"/usr/bin/curl -u admin:{_PASSWORD} https://x", "/usr/bin/curl -u admin:*** https://x"),
            (f"curl.exe -u admin:{_PASSWORD} https://x", "curl.exe -u admin:*** https://x"),
            (f"curl -u admin:{_PASSWORD}", "curl -u admin:***"),
            (f"curl -u :{_PASSWORD} https://x", "curl -u :*** https://x"),
            ("curl -u admin:pa:ss:word https://x", "curl -u admin:*** https://x"),
        ],
    )  # fmt: skip
    def test_the_password_is_masked_and_the_rest_of_the_command_is_kept(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    def test_the_command_inside_a_json_string_is_masked(self) -> None:
        record = json.dumps({"command": f"curl -u admin:{_PASSWORD} https://x", "exit_code": 0})
        masked = _masked(record)
        assert _PASSWORD not in masked
        assert json.loads(masked) == {"command": "curl -u admin:*** https://x", "exit_code": 0}

    @pytest.mark.parametrize(
        "command",
        [
            "curl -u admin:$PASSWORD https://x",
            "curl -u admin:${API_PASS} https://x",
            'curl -u "admin:$PASSWORD" https://x',
            "curl -u admin:$(cat pw.txt) https://x",
            "curl -u admin https://x",
            "curl -u admin: https://x",
            "curl -u $CREDENTIALS https://x",
            "curl -u admin:*** https://x",
            "curl --upload-file a.txt https://x",
            "curl -sS https://x | sort -u a:b",
            "curl -sS https://x && git push -u origin:main",
            "echo curl; sort -u a:b",
            "mycurl -u admin:pw https://x",
            "sort -u admin:pw",
        ],
    )  # fmt: skip
    def test_a_reference_a_missing_password_and_other_commands_stay_readable(self, command: str) -> None:
        assert _masked(command) == command


class TestCurlCookie:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"curl -b '{_COOKIES}' https://x", "curl -b '***' https://x"),
            (f'curl -b "{_COOKIES}" https://x', 'curl -b "***" https://x'),
            (f"curl --cookie '{_COOKIES}' https://x", "curl --cookie '***' https://x"),
            ("curl -b sid=abcDEF123456 https://x", "curl -b *** https://x"),
            (f"curl https://x -b '{_COOKIES}' -o out", "curl https://x -b '***' -o out"),
        ],
    )  # fmt: skip
    def test_the_cookie_string_is_masked_whole(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    def test_the_command_inside_a_json_string_is_masked(self) -> None:
        record = json.dumps({"command": f'curl -b "{_COOKIES}" https://x'})
        masked = _masked(record)
        assert "abcDEF123456" not in masked
        assert "theme" not in masked
        assert json.loads(masked) == {"command": 'curl -b "***" https://x'}

    @pytest.mark.parametrize(
        "command",
        [
            "curl -b cookies.txt https://x",
            "curl -b ./jar/cookies https://x",
            'curl -b "$COOKIE" https://x',
            "curl -b $SESSION_COOKIE https://x",
            "curl -b '***' https://x",
            "curl -sS https://x && grep -b a=b notes.txt",
            "grep -b sid=abc notes.txt",
        ],
    )  # fmt: skip
    def test_a_cookie_jar_file_a_reference_and_other_commands_stay_readable(self, command: str) -> None:
        assert _masked(command) == command


class TestSshpass:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"sshpass -p {_PASSWORD} ssh root@10.0.0.5 uptime", "sshpass -p *** ssh root@10.0.0.5 uptime"),
            (f"sshpass -p'{_PASSWORD}' ssh root@host", "sshpass -p'***' ssh root@host"),
            (f"sshpass -p '{_PASSWORD} x' ssh root@host", "sshpass -p '***' ssh root@host"),
            (f'sshpass -p "{_PASSWORD}" scp a root@host:/b', 'sshpass -p "***" scp a root@host:/b'),
            (f"sshpass -p{_PASSWORD} ssh root@host", "sshpass -p*** ssh root@host"),
            (f"sshpass -v -p {_PASSWORD} ssh root@host", "sshpass -v -p *** ssh root@host"),
            (f"/usr/bin/sshpass -p {_PASSWORD} ssh root@host", "/usr/bin/sshpass -p *** ssh root@host"),
        ],
    )  # fmt: skip
    def test_the_password_is_masked_and_the_ssh_command_is_kept(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            'sshpass -p "$SSH_PASSWORD" ssh root@host',
            "sshpass -p $SSH_PASSWORD ssh root@host",
            "sshpass -f pw.txt ssh root@host",
            "sshpass -e ssh root@host",
            "sshpass -P assword ssh root@host",
            "sshpass -p *** ssh root@host",
            "ssh -p 22 root@host",
            "scp -P 22 a root@host:/b",
            "sshpass is a tool; use ssh -p 2222 instead",
            "the options sshpass -p, mysql -p) and curl -u: are described below",
        ],
    )  # fmt: skip
    def test_a_reference_a_file_an_environment_variable_and_other_commands_stay_readable(self, command: str) -> None:
        assert _masked(command) == command


class TestMysqlFamily:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"mysql -u root -p{_PASSWORD} -h 10.0.0.5 shop", "mysql -u root -p*** -h 10.0.0.5 shop"),
            (f"mysqldump -uroot -p{_PASSWORD} shop > dump.sql", "mysqldump -uroot -p*** shop > dump.sql"),
            (f"mysqladmin -u root -p{_PASSWORD} status", "mysqladmin -u root -p*** status"),
            (f"mysql -u root -p'{_PASSWORD}' shop", "mysql -u root -p'***' shop"),
            (f'mysql -u root -p"{_PASSWORD}" shop', 'mysql -u root -p"***" shop'),
            (f"mysql shop -u root -p{_PASSWORD}", "mysql shop -u root -p***"),
        ],
    )  # fmt: skip
    def test_the_attached_password_is_masked_and_the_rest_is_kept(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "mysql -u root -p shop",
            "mysql -u root -p",
            "mysql -u root -p -h host",
            "mysql -p$MYSQL_PASSWORD shop",
            'mysql -p"$MYSQL_PASSWORD" shop',
            "mysql -u root -p*** shop",
            "mysql -u root -P 3306 -h host shop",
            "psql -p 5432 -U app shop",
            "nc -p4444 host",
            "use `sshpass -p`、`mysql -p` to connect",
        ],
    )  # fmt: skip
    def test_a_prompt_a_reference_a_port_and_other_commands_stay_readable(self, command: str) -> None:
        assert _masked(command) == command


class TestOneCommandAtATime:
    @pytest.mark.parametrize("separator", ["|", ";", "&&", "||", "\n"])
    def test_an_option_after_a_command_separator_belongs_to_the_next_command(self, separator: str) -> None:
        command = f"curl https://x {separator} sort -u admin:{_PASSWORD}"
        assert _masked(command) == command

    def test_an_escaped_line_break_in_a_json_string_separates_two_commands(self) -> None:
        record = json.dumps({"command": f"curl https://x\nsort -u admin:{_PASSWORD}"})
        assert _masked(record) == record

    def test_a_credential_after_a_quoted_argument_with_separators_is_still_in_the_same_command(self) -> None:
        command = f"curl -H 'X: a;b|c&d' -u admin:{_PASSWORD} https://x"
        assert _masked(command) == "curl -H 'X: a;b|c&d' -u admin:*** https://x"

    def test_two_commands_on_one_record_are_each_masked(self) -> None:
        command = f"curl -u a:{_PASSWORD} https://x && sshpass -p {_PASSWORD} ssh h"
        assert _masked(command) == "curl -u a:*** https://x && sshpass -p *** ssh h"

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"curl -s curl -u admin:{_PASSWORD} https://x", "curl -s curl -u admin:*** https://x"),
            (f"curl https://x/curl-demo -u admin:{_PASSWORD}", "curl https://x/curl-demo -u admin:***"),
            (f"curl 'curl' -u admin:{_PASSWORD} https://x", "curl 'curl' -u admin:*** https://x"),
            (f"sshpass sshpass -p {_PASSWORD} ssh h", "sshpass sshpass -p *** ssh h"),
            (f"mysql mysqldump -p{_PASSWORD} db", "mysql mysqldump -p*** db"),
        ],
    )  # fmt: skip
    def test_a_later_occurrence_of_the_command_name_does_not_hide_the_credential(
        self, command: str, expected: str
    ) -> None:
        assert _masked(command) == expected


class TestPipelineBehaviour:
    @pytest.mark.parametrize(
        "command",
        [
            f"curl -u admin:{_PASSWORD} https://x",
            f"curl -b '{_COOKIES}' https://x",
            f"sshpass -p {_PASSWORD} ssh root@host",
            f"mysql -u root -p{_PASSWORD} shop",
        ],
    )  # fmt: skip
    def test_masking_twice_changes_nothing(self, command: str) -> None:
        once = _masked(command)
        assert _masked(once) == once

    def test_in_source_mode_the_command_is_masked_on_every_line(self) -> None:
        """Anchored on a command name, the rules do not mistake a variable name for a credential, so a source file
        needs no string literal to trigger them."""
        comment = f"# curl -u admin:{_PASSWORD} https://x"
        literal = f'cmd = "curl -u admin:{_PASSWORD} https://x"'
        assert _masked(comment, source_code=True) == "# curl -u admin:*** https://x"
        assert _masked(literal, source_code=True) == 'cmd = "curl -u admin:*** https://x"'

    def test_a_text_without_any_of_the_commands_is_returned_unchanged(self) -> None:
        text = "echo hello -u a:b -p secret -b x=y"
        assert _masked(text) == text


class TestCostStaysLinear:
    """A long record that repeats the command name does a bounded amount of work per occurrence."""

    @pytest.mark.parametrize("unit", ["curl ", "curl -u ", "sshpass -p ", "mysql -p", "curl 'a;b' ", 'curl "'])
    def test_a_long_run_of_the_command_name_is_masked_in_proportional_time(self, unit: str) -> None:
        def seconds(repeats: int) -> float:
            text = unit * repeats
            start = time.process_time()
            redact_sensitive_text(text)
            return time.process_time() - start

        small = min(seconds(4_000) for _ in range(3))
        large = min(seconds(16_000) for _ in range(3))
        assert large < max(small * 12, 0.5)

    @pytest.mark.parametrize("name", ["curl", "sshpass", "mysql"])
    def test_a_text_that_repeats_the_command_name_costs_about_as_much_as_any_other_text(self, name: str) -> None:
        """The next occurrence of the name ends the search from the previous one, so each occurrence costs a few steps, not
        the whole 256-character bound; the other passes cost the same for any word, which is the yardstick."""

        def seconds(word: str) -> float:
            text = f"{word} " * 20_000
            start = time.process_time()
            redact_sensitive_text(text)
            return time.process_time() - start

        other = min(seconds("word") for _ in range(3))
        repeated = min(seconds(name) for _ in range(3))
        assert repeated < other * 3 + 0.1
