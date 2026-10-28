"""structured_fields: credential-named fields in JSON, JSON-in-JSON and Python repr diagnostics.

Each case is a shape a tool result really takes: OAuth token responses (snake, camel and kebab spellings), config
dumps with provider-prefixed names, MCP results that wrap a JSON document in a JSON string, and pytest failures that
print a settings dict. The keep-lists pin what must stay readable: pagination cursors, metadata and source code.
"""

from __future__ import annotations

import json
import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.core.security.redact.structured_fields import _is_secret_field_name

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
        ],
    )  # fmt: skip
    def test_credential_names_match(self, name: str) -> None:
        assert _is_secret_field_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            "key", "tokenizer", "author", "nextPageToken", "pageToken", "csrfToken", "token_count", "max_tokens",
            "password_policy", "passwordHint", "secretary", "status", "credentials", "githubToken", "keyboard",
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

    @pytest.mark.parametrize(
        ("key", "label"),
        [("feishuAppSecret", "App Secret"), ("telegram_bot_token", "Telegram-Bot-Token"), ("signingSecret", "Signing Secret")],
    )  # fmt: skip
    def test_form_labels_keyed_by_channel_credential_names_stay_readable(self, key: str, label: str) -> None:
        """The locale files of this very repo carry such keys; masking the labels would blind an agent editing them."""
        text = json.dumps({key: label}, indent=2)
        assert redact_sensitive_text(text) == text


class TestBoundedWork:
    def test_field_past_the_chunk_threshold_is_masked(self) -> None:
        text = "x" * 40_000 + _json("refreshToken") + "y" * 100
        assert _OPAQUE not in redact_sensitive_text(text)

    def test_long_run_of_name_characters_stays_linear(self) -> None:
        text = '"' + "a" * 60_000 + '"' + " " + "b" * 60_000
        start = time.perf_counter()
        redact_sensitive_text(text)
        assert time.perf_counter() - start < 2.0

    def test_many_quotes_stay_linear(self) -> None:
        text = '"aaaaaaaaaaaaaaaa' * 8_000
        start = time.perf_counter()
        redact_sensitive_text(text)
        assert time.perf_counter() - start < 2.0
