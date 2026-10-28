"""Variable references in credential-named values: a reference names a variable and holds no secret.

Compose files, config templates and scripts say ``POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set it in .env}``; masking
that mangles the variable name the reader needs. Only a value that is entirely a reference is kept. A default after
``:-`` is a literal, a real secret that merely starts with ``$`` must still be masked, and so must a mix of reference
and literal.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text


class TestReferencesStayReadable:
    @pytest.mark.parametrize(
        "text",
        [
            "OPENAI_API_KEY=$OPENAI_API_KEY",
            "DB_PASSWORD=${DB_PASSWORD}",
            "DB_PASSWORD=${db_pass}",
            "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}",
            "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD?required}",
            'api_key: "${API_KEY}"',
            "--password=${DB_PASSWORD}",
            '{"apiKey": "${OPENAI_API_KEY}"}',
            '{"clientSecret": "$CLIENT_SECRET"}',
        ],
    )
    def test_whole_value_reference_is_kept(self, text: str) -> None:
        assert redact_sensitive_text(text) == text


class TestSecretsStayMasked:
    @pytest.mark.parametrize(
        ("text", "secret"),
        [
            ("PASSWORD=$Secret123", "$Secret123"),
            ("PASSWORD=$uperpass", "$uperpass"),
            ("DB_PASSWORD=${DB_PASSWORD:-changeme-Zk3f9Q}", "changeme-Zk3f9Q"),
            ("PASSWORD=${DB}Zk3fQ9xLm2Vb7TnW", "Zk3fQ9xLm2Vb7TnW"),
            ("password: $2b$12$KIXx8Zr1l0uG5hYq3w9pQe7vJm2nB4cD6fH8jL0sT", "KIXx8Zr1l0uG5hYq3w9pQe7vJm2nB4cD6fH8jL0sT"),
            ("SECRET=Zk3f$Q9xLm2Vb7TnWc4Rp", "Zk3f$Q9xLm2Vb7TnWc4Rp"),
            ('{"apiKey": "$Secret123"}', "$Secret123"),
            ('{"apiKey": "${X:-realSecretValue12345}"}', "realSecretValue12345"),
        ],
    )  # fmt: skip
    def test_literal_values_are_masked(self, text: str, secret: str) -> None:
        assert secret not in redact_sensitive_text(text)
