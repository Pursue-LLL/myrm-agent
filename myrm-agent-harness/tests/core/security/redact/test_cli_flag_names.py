"""The name of a command line flag that carries a credential: ``--db-password``, ``--client-secret``, ``--auth-token``.

A flag is a credential when its name ends in a word that says so (``password``, ``secret``, ``api-key``, ``access-key``)
or in ``token`` behind a word that makes it one (``auth-token``, ``bot-token``). A name that only contains such a word
(``--password-file``, ``--secret-name``, ``--tokenizer``), asks for no credential (``--no-password``) or is a plain token
of the program (``--failure-token``) keeps its argument readable.
"""

from __future__ import annotations

import json
import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.core.security.redact.bounded_replace import _replace_pattern_bounded
from myrm_agent_harness.core.security.redact.patterns import _CLI_FLAG_RE, _redact_cli_flag

_SECRET = "s3cretPw99xyz"

# The names a credential flag has always had: they stay masked in every form.
_FLAGS_MASKED_BEFORE = (
    "--api-key",
    "--api_key",
    "--apikey",
    "--hook-token",
    "--hook_token",
    "--token",
    "--secret",
    "--password",
    "--passwd",
    "--passphrase",
    "--pass-phrase",
)

_FLAGS_OF_A_CREDENTIAL = (
    "--db-password",
    "--root-password",
    "--new-password",
    "--proxy-password",
    "--registry-password",
    "--ssh-passphrase",
    "--key-passphrase",
    "--client-secret",
    "--shared-secret",
    "--webhook-secret",
    "--access-key",
    "--secret-key",
    "--secret-access-key",
    "--aws-secret-access-key",
    "--access-token",
    "--auth-token",
    "--authtoken",
    "--refresh-token",
    "--bot-token",
    "--session-token",
    "--api-token",
    "--private-token",
    "--id-token",
)

_ALL_FLAGS = _FLAGS_MASKED_BEFORE + _FLAGS_OF_A_CREDENTIAL


@pytest.mark.parametrize("flag", _ALL_FLAGS)
class TestTheCredentialIsMasked:
    def test_after_a_space(self, flag: str) -> None:
        out = redact_sensitive_text(f"tool {flag} {_SECRET} --verbose")
        assert _SECRET not in out
        assert out.startswith(f"tool {flag} ")
        assert out.endswith(" --verbose")

    def test_after_an_equals_sign(self, flag: str) -> None:
        out = redact_sensitive_text(f"tool {flag}={_SECRET} --verbose")
        assert _SECRET not in out
        assert out.startswith(f"tool {flag}=")
        assert out.endswith(" --verbose")

    def test_in_quotes(self, flag: str) -> None:
        for quote in ("'", '"'):
            out = redact_sensitive_text(f"tool {flag} {quote}{_SECRET} x{quote} --verbose")
            assert _SECRET not in out
            assert out.count(quote) == 2

    def test_in_upper_case(self, flag: str) -> None:
        assert _SECRET not in redact_sensitive_text(f"tool {flag.upper()} {_SECRET}")

    def test_inside_a_json_string(self, flag: str) -> None:
        text = json.dumps({"command": f"tool {flag} {_SECRET} --verbose"})
        assert _SECRET not in redact_sensitive_text(text)

    def test_masking_twice_changes_nothing(self, flag: str) -> None:
        once = redact_sensitive_text(f"tool {flag} {_SECRET}")
        assert redact_sensitive_text(once) == once


class TestReadableArguments:
    @pytest.mark.parametrize(
        "text",
        [
            "docker login --password-stdin registry.example.com",
            "tool --password-file /run/secrets/pw",
            "tool --token-file /run/secrets/tok",
            "tool --secret-name db-credentials",
            "tool --secret-ref vault/db",
            "tool --tokenizer gpt2",
            "psql --no-password dbname",
            "tool --skip-password check.py",
            "tool --disable-secret run.py",
            "tool --without-password run.py",
            "tool --expected-command-token run.py",
            "tool --failure-token FAIL",
            "tool --max-token 512",
            "tool --stop-token END",
            "redis-cli -p 6379",
            "docker run -p 8080:80 nginx",
            "sshpass -e ssh -p 2222 host",
            "tool --password $DB_PASSWORD",
            "tool --db-password ${DB_PASSWORD}",
            "tool --auth-token ***",
        ],
    )  # fmt: skip
    def test_the_text_stays_as_it_is(self, text: str) -> None:
        assert redact_sensitive_text(text) == text


class TestTheFlagNameKeepsItsShape:
    def test_only_the_value_is_masked(self) -> None:
        out = redact_sensitive_text(f"tool --db-password {_SECRET} --db-user admin --client-secret={_SECRET}")
        assert _SECRET not in out
        assert "--db-user admin" in out
        assert "--client-secret=" in out

    def test_a_credential_flag_is_masked_each_time_it_occurs(self) -> None:
        out = redact_sensitive_text(f"a --auth-token {_SECRET} b --access-key {_SECRET} c --secret-key={_SECRET}")
        assert _SECRET not in out

    def test_the_password_of_a_human_is_hidden_completely(self) -> None:
        assert redact_sensitive_text(f"tool --db-password {_SECRET}") == "tool --db-password ***"


class TestCostStaysLinear:
    """A long run of flag-like words costs time in proportion to its length: the flag pass is timed on its own, since the
    other passes of the pipeline cost far more on such text and would hide it."""

    @pytest.mark.parametrize(
        "unit",
        ["--a-b-c-d-e-f-g-h ", "--" + "x-" * 40, "--auth-", "--token " + "a" * 40 + " ", "--db-password "],
    )  # fmt: skip
    def test_a_long_run_of_flag_like_words_is_masked_in_proportional_time(self, unit: str) -> None:
        def seconds(repeats: int) -> float:
            text = unit * repeats
            start = time.process_time()
            _replace_pattern_bounded(text, _CLI_FLAG_RE, _redact_cli_flag)
            return time.process_time() - start

        small = min(seconds(4_000) for _ in range(3))
        large = min(seconds(16_000) for _ in range(3))
        assert large < max(small * 12, 0.5)
