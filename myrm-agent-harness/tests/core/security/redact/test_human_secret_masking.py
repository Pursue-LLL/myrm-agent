"""A password or passphrase is hidden completely; a machine-issued token keeps its head and tail.

``correc...aple`` hands over the first word of ``correct-horse-battery-staple`` and most of the last, so a value a
person chose is masked as ``***`` in every shape the redactor detects it in, whatever its length. A random token keeps
six characters at the head (the issuer's prefix) and four at the tail, which discloses nothing usable.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.core.security.redact.masking import _mask_secret

_PHRASE = "correct-horse-battery-staple"
_TOKEN = "abcdefghijklmnopqrstuvwxyz"
_TOKEN_MASKED = "abcdef...wxyz"

_PHRASE_SHAPES: dict[str, str] = {
    "env-export": f"export BORG_PASSPHRASE={_PHRASE}",
    "env-quoted": f'DB_PASSWORD="{_PHRASE}"',
    "env-passwd": f"PASSWD={_PHRASE}",
    "env-lower": f"db_pw={_PHRASE}",
    "yaml": f"vault_passphrase: {_PHRASE}",
    "yaml-quoted": f'ssh_passphrase: "{_PHRASE}"',
    "cli-space": f"gpg --batch --passphrase {_PHRASE} -d secrets.gpg",
    "cli-equals": f"mysql --password={_PHRASE} -u root",
    "json": json.dumps({"userPassword": _PHRASE, "host": "backup.example"}),
    "json-in-json": json.dumps({"output": json.dumps({"password": _PHRASE})}),
    "repr": f"E   assert {{'passphrase': '{_PHRASE}'}} == {{}}",
    "url-query": f"https://backup.example/restore?passphrase={_PHRASE}&dest=/tmp",
    "form-body": f"password={_PHRASE}&user=bob",
}

_TOKEN_SHAPES: dict[str, str] = {
    "env-export": f"export GH_TOKEN={_TOKEN}",
    "env-lower": f"openai_key={_TOKEN}",
    "yaml": f"api_key: {_TOKEN}",
    "cli-space": f"deploy --api-key {_TOKEN} --force",
    "json": json.dumps({"api_key": _TOKEN, "host": "api.example"}),
    "form-body": f"token={_TOKEN}&user=bob",
}


class TestHumanSecretIsHiddenCompletely:
    @pytest.mark.parametrize("shape", _PHRASE_SHAPES)
    def test_long_value_is_masked_whole(self, shape: str) -> None:
        text = _PHRASE_SHAPES[shape]
        assert redact_sensitive_text(text) == text.replace(_PHRASE, "***")

    def test_quotes_around_the_value_are_kept(self) -> None:
        assert redact_sensitive_text(f'DB_PASSWORD="{_PHRASE}"') == 'DB_PASSWORD="***"'


class TestTokenKeepsHeadAndTail:
    @pytest.mark.parametrize("shape", _TOKEN_SHAPES)
    def test_long_token_is_masked_in_the_middle(self, shape: str) -> None:
        text = _TOKEN_SHAPES[shape]
        assert redact_sensitive_text(text) == text.replace(_TOKEN, _TOKEN_MASKED)


class TestMaskSecret:
    def test_name_decides_between_complete_and_partial_masking(self) -> None:
        assert _mask_secret("passphrase", _PHRASE) == "***"
        assert _mask_secret("--password=", _PHRASE) == "***"
        assert _mask_secret("DB_PW", _PHRASE) == "***"
        assert _mask_secret("API_TOKEN", _TOKEN) == _TOKEN_MASKED

    def test_name_that_merely_contains_pass_is_hidden_completely(self) -> None:
        assert _mask_secret("bypass_token", _TOKEN) == "***"

    def test_short_value_is_hidden_completely_whatever_the_name(self) -> None:
        assert _mask_secret("API_TOKEN", "short") == "***"
