"""structured_fields: credential-named fields in JSON, JSON-in-JSON and Python repr diagnostics.

Each case is a shape a tool result really takes: OAuth token responses (snake, camel and kebab spellings), config
dumps with provider-prefixed names, MCP results that wrap a JSON document in a JSON string, and pytest failures that
print a settings dict. The keep-lists pin what must stay readable: pagination cursors, metadata, form labels and source code.
"""

from __future__ import annotations

import json
import random
import re
import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.core.security.redact.structured_fields import (
    _FIELD_NAME,
    _JSON_ESCAPED_FIELD_RE,
    _is_secret_field_name,
)

_OPAQUE = "opaqueValue1234567890abcdef"


def _json(key: str) -> str:
    return f'{{"{key}":"{_OPAQUE}"}}'


class TestFieldNamePolicy:
    @pytest.mark.parametrize(
        "name",
        [
            "token", "secret", "bearer", "password", "passwd", "authorization", "Proxy-Authorization", "cookie", "set-cookie",
            "api_key", "apiKey", "api-key", "x-api-key", "api_token", "client_secret", "clientSecret", "client-secret",
            "access_token", "accessToken", "refresh_token", "refreshToken", "id_token", "idToken", "auth_token",
            "private_key", "privateKey", "secret_key", "secret_value", "raw_secret", "secret_input", "key_material",
            "stripeSecretKey", "openaiApiKey", "dbPassword", "UserPassword", "sessionToken", "BRAVE_API_KEY",
            "SecretAccessKey", "secret_access_key", "aws_secret_access_key",
            "passphrase", "ssh_passphrase", "keyStorePassPhrase", "pass-phrase",
            "appSecret", "app_secret", "feishuAppSecret", "signingSecret", "signing-secret", "SLACK_SIGNING_SECRET",
            "botToken", "bot_token", "telegram_bot_token", "verificationToken", "verification_token",
        ],
    )  # fmt: skip
    def test_credential_names_match(self, name: str) -> None:
        assert _is_secret_field_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            "key", "tokenizer", "author", "nextPageToken", "pageToken", "csrfToken", "token_count", "max_tokens",
            "password_policy", "passwordHint", "passphraseHint", "passphrase_required", "secretary", "status",
            "credentials", "githubToken", "keyboard",
            "file_token", "page_token", "nextToken", "cancel_token", "reply_token", "context_token", "state_token",
            "app_id", "app_name", "webhook_url", "secret_name", "bot_name", "signing_algorithm",
        ],
    )  # fmt: skip
    def test_metadata_and_cursor_names_do_not_match(self, name: str) -> None:
        assert not _is_secret_field_name(name)


class TestPlainJson:
    @pytest.mark.parametrize(
        "key",
        ["refreshToken", "clientSecret", "idToken", "privateKey", "accessToken", "client_secret", "id_token",
         "private_key", "refresh-token", "x-api-key", "stripeSecretKey", "dbPassword", "authorization", "Set-Cookie"],
    )  # fmt: skip
    def test_value_is_masked_and_key_is_kept(self, key: str) -> None:
        out = redact_sensitive_text(_json(key))
        assert _OPAQUE not in out
        assert f'"{key}"' in out

    def test_names_masked_before_stay_masked(self) -> None:
        for key in ("api_key", "token", "secret", "password", "access_token", "refresh_token", "auth_token", "bearer"):
            assert _OPAQUE not in redact_sensitive_text(_json(key))

    def test_neighbouring_fields_are_untouched(self) -> None:
        text = f'{{"name":"keepme","refreshToken":"{_OPAQUE}","nextPageToken":"CAEQAA","tokenizer":"gpt2"}}'
        out = redact_sensitive_text(text)
        assert '"name":"keepme"' in out
        assert '"nextPageToken":"CAEQAA"' in out
        assert '"tokenizer":"gpt2"' in out

    @pytest.mark.parametrize("key", ["apiKey", "api_key", "token", "clientSecret", "Authorization"])
    @pytest.mark.parametrize("empty", ['""', '"   "'])
    def test_empty_value_stays_readable(self, key: str, empty: str) -> None:
        text = f'{{"{key}": {empty}}}'
        assert redact_sensitive_text(text) == text

    def test_escaped_quote_inside_value_is_captured_whole(self) -> None:
        out = redact_sensitive_text(r'{"clientSecret": "my\"secretvalue1234567890tail"}')
        assert out == r'{"clientSecret": "my\"se...tail"}'

    def test_unlisted_provider_token_without_a_vendor_prefix_is_not_guessed(self) -> None:
        assert _OPAQUE in redact_sensitive_text(_json("githubToken"))


class TestJsonInsideJsonString:
    def test_wrapped_document_is_masked_at_depth_one(self) -> None:
        text = (
            r'{"output": "{\"api_key\": \"'
            + _OPAQUE
            + r"\", \"refreshToken\": \""
            + _OPAQUE
            + r'\", \"name\": \"keepme\"}"}'
        )
        out = redact_sensitive_text(text)
        assert _OPAQUE not in out
        assert r"\"name\": \"keepme\"" in out
        assert out.startswith('{"output": "{') and out.endswith('}"}')

    def test_wrapped_document_is_masked_at_depth_two(self) -> None:
        text = r'{"a": "{\"b\": \"{\\\"password\\\": \\\"' + _OPAQUE + r'\\\"}\"}"}'
        out = redact_sensitive_text(text)
        assert _OPAQUE not in out
        assert r"\\\"password\\\"" in out

    def test_non_credential_wrapped_field_is_untouched(self) -> None:
        text = r'{"output": "{\"token_count\": \"5\"}"}'
        assert redact_sensitive_text(text) == text


class TestPythonReprDiagnostics:
    def test_pytest_assertion_line_is_masked(self) -> None:
        line = f"E       AssertionError: assert {{'client_secret': '{_OPAQUE}', 'name': 'keepme'}} == {{}}"
        out = redact_sensitive_text(line)
        assert _OPAQUE not in out
        assert "'name': 'keepme'" in out

    def test_final_exception_line_masks_single_and_double_quoted_values(self) -> None:
        line = f"ValueError: bad {{'BRAVE_API_KEY': '{_OPAQUE}', 'sessionToken': \"{_OPAQUE}\"}}"
        assert _OPAQUE not in redact_sensitive_text(line)

    def test_dotted_exception_class_is_a_diagnostic_line(self) -> None:
        line = f"requests.exceptions.HTTPError: {{'password': '{_OPAQUE}'}}"
        assert _OPAQUE not in redact_sensitive_text(line)

    def test_source_code_literal_is_left_as_written(self) -> None:
        line = f"config = {{'password': '{_OPAQUE}', 'client_secret': '{_OPAQUE}'}}"
        assert redact_sensitive_text(line) == line

    def test_non_credential_entries_on_a_diagnostic_line_are_kept(self) -> None:
        line = "KeyError: {'token_count': 'abc', 'name': 'keepme'}"
        assert redact_sensitive_text(line) == line


class TestCloudCredentials:
    """Credential fields a cloud CLI prints."""

    def test_aws_session_output_masks_the_secret_access_key(self) -> None:
        text = json.dumps(
            {
                "Credentials": {
                    "AccessKeyId": "ASIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "SessionToken": "IQoJb3JpZ2luX2VjEJr" + "x" * 60,
                    "Expiration": "2026-10-28T12:00:00Z",
                }
            },
            indent=2,
        )
        out = redact_sensitive_text(text)
        assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in out
        assert "x" * 20 not in out
        assert '"Expiration": "2026-10-28T12:00:00Z"' in out

    @pytest.mark.parametrize(
        "key", ["file_token", "page_token", "nextToken", "cancel_token", "reply_token", "context_token", "state_token", "app_id"]
    )  # fmt: skip
    def test_identifiers_named_like_tokens_stay_readable(self, key: str) -> None:
        text = json.dumps({key: _OPAQUE})
        assert redact_sensitive_text(text) == text


_CHANNEL_KEYS = [
    "feishuAppSecret",
    "app_secret",
    "signingSecret",
    "SLACK_SIGNING_SECRET",
    "telegram_bot_token",
    "botToken",
    "verificationToken",
]
_REAL_VALUES = [
    _OPAQUE,
    "Zk3fQ9xLm2Vb7TnWc4RpAa8sD5fG1hJ0",
    "123456789:AAEhBP0av18F1UXjpT9bHqkYzQ2xLmN8vWc",
    "abcdefghijklmnopqrstuvwxyz",
]


class TestChannelCredentials:
    """Channel credential names are credentials, yet locale files key their form labels by the very same names."""

    @pytest.mark.parametrize("key", _CHANNEL_KEYS)
    @pytest.mark.parametrize("value", _REAL_VALUES)
    def test_real_value_is_masked_in_every_shape(self, key: str, value: str) -> None:
        plain = json.dumps({key: value})
        wrapped = json.dumps({"output": plain})
        diagnostic = f"AssertionError: {{{key!r}: {value!r}}}"
        for text in (plain, wrapped, diagnostic):
            out = redact_sensitive_text(text)
            assert value not in out
            assert key in out

    @pytest.mark.parametrize("key", _CHANNEL_KEYS)
    @pytest.mark.parametrize(
        "label", ["App Secret", "Telegram-Bot-Token", "Signing Secret", "bot_token", "your-bot-token", "Token", "应用密钥", "ボットトークン"]
    )  # fmt: skip
    def test_form_label_stays_readable_in_every_shape(self, key: str, label: str) -> None:
        """The locale files of this very repo carry such keys; masking the labels would blind an agent editing them."""
        plain = json.dumps({key: label}, indent=2, ensure_ascii=False)
        wrapped = json.dumps({"output": json.dumps({key: label}, ensure_ascii=False)}, ensure_ascii=False)
        diagnostic = f"AssertionError: {{{key!r}: {label!r}}}"
        for text in (plain, wrapped, diagnostic):
            assert redact_sensitive_text(text) == text

    @pytest.mark.parametrize(
        "value", ["abcdefghijklmnopqrst", "abcdefghijklmnopqrstuvwxyz", "Secret1", "token_2", "ab:cd"]
    )
    def test_value_that_is_not_a_label_is_masked(self, value: str) -> None:
        """Twenty letters or more in one word, a digit or any other character is no form label."""
        assert value not in redact_sensitive_text(json.dumps({"appSecret": value}))

    @pytest.mark.parametrize(
        "key", ["password", "passphrase", "api_key", "clientSecret", "bot_access_token", "secret", "authorization"]
    )
    def test_unambiguous_names_mask_a_label_shaped_value(self, key: str) -> None:
        """Only channel credential names get the label exemption; a password such as ``hunter two`` stays masked."""
        assert "hunter two" not in redact_sensitive_text(json.dumps({key: "hunter two"}))

    def test_variable_reference_and_empty_value_stay_readable(self) -> None:
        for text in ('{"appSecret": "${APP_SECRET}"}', '{"botToken": ""}'):
            assert redact_sensitive_text(text) == text


class TestBoundedWork:
    def test_field_past_the_chunk_threshold_is_masked(self) -> None:
        text = "x" * 40_000 + _json("refreshToken") + "y" * 100
        assert _OPAQUE not in redact_sensitive_text(text)

    def test_long_run_of_name_characters_stays_linear(self) -> None:
        text = '"' + "a" * 60_000 + '"' + " " + "b" * 60_000
        start = time.process_time()
        redact_sensitive_text(text)
        assert time.process_time() - start < 2.0

    def test_many_quotes_stay_linear(self) -> None:
        text = '"aaaaaaaaaaaaaaaa' * 8_000
        start = time.process_time()
        redact_sensitive_text(text)
        assert time.process_time() - start < 2.0


class TestEscapedFieldInsideJsonString:
    """A JSON document inside a JSON string has every quote behind a run of backslashes: one per nesting level, doubled
    again for each level it is nested in. Both quotes of the key and the value carry the same run."""

    @pytest.mark.parametrize("backslashes", [1, 2, 3, 5, 7, 15])
    def test_a_field_is_masked_at_any_depth(self, backslashes: int) -> None:
        quote = "\\" * backslashes + '"'
        text = f"{{{quote}password{quote}:{quote}{_OPAQUE}{quote}}}"
        result = redact_sensitive_text(text)
        assert _OPAQUE not in result
        assert "password" in result

    @pytest.mark.parametrize("backslashes", [1, 3, 7])
    def test_the_fields_around_it_stay_readable(self, backslashes: int) -> None:
        quote = "\\" * backslashes + '"'
        text = f"{{{quote}user{quote}:{quote}alice{quote},{quote}password{quote}:{quote}{_OPAQUE}{quote}}}"
        result = redact_sensitive_text(text)
        assert _OPAQUE not in result
        assert f"{quote}user{quote}:{quote}alice{quote}" in result

    def test_a_key_that_opens_with_a_longer_run_than_it_closes_with_is_no_field(self) -> None:
        """Both runs of an encoded key are equal; an extra backslash in front belongs to the text before the key."""
        assert _JSON_ESCAPED_FIELD_RE.search('\\\\\\"password\\\\":\\\\"x\\\\"') is None

    def test_a_match_starts_where_a_run_of_backslashes_starts(self) -> None:
        """The pattern is the unanchored one restricted to the start of a run, so it does not retry every offset of a run."""
        unanchored = re.compile(rf'((\\+)"{_FIELD_NAME}\2")\s*:\s*\2"([^"\\]+)\2"', re.IGNORECASE)
        rng = random.Random(7)
        alphabet = ["\\", "\\", '"', ":", "password", "x", " ", "{"]
        for _ in range(20_000):
            text = "".join(rng.choices(alphabet, k=rng.randint(1, 14)))
            for offset in range(len(text)):
                starts_a_run = text[offset] == "\\" and (offset == 0 or text[offset - 1] != "\\")
                expected = unanchored.match(text, offset) if starts_a_run else None
                found = _JSON_ESCAPED_FIELD_RE.match(text, offset)
                assert (found.span() if found else None) == (expected.span() if expected else None), text


class TestRunOfBackslashesStaysLinear:
    """Every offset inside a run once started a match attempt of its own, so a run cost time in proportion to its square."""

    def test_the_pattern_alone_is_linear_in_the_run(self) -> None:
        text = "\\" * 64_000 + '"'
        start = time.process_time()
        _JSON_ESCAPED_FIELD_RE.search(text)
        assert time.process_time() - start < 0.5

    def test_the_whole_redactor_is_linear_in_the_run(self) -> None:
        text = "\\" * 64_000 + '"'
        start = time.process_time()
        redact_sensitive_text(text)
        assert time.process_time() - start < 1.0
