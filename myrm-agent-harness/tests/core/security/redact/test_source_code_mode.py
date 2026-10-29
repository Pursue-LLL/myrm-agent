"""The redactor in source mode: code names credentials constantly and keeps a secret only as a string literal.

Redacting a source file in full turned ``total_api_tokens = 0`` into ``total_api_tokens=***`` and
``completion_tokens: int | None = None`` into ``completion_tokens: *** | None = None``: about a quarter of the files of
this code base read back as broken code, so an edit copied from the read no longer matched the file. In source mode
the name-based assignment passes run on the lines that carry a string literal, and every value-shape pass runs on
every line.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_CODE_LINES = (
    "total_api_tokens = 0",
    "completion_tokens: int | None = None",
    "    password: str",
    "    api_key: Optional[str] = None",
    "credentials: dict[str, str] | None = None",
    "password = get_password(user)",
    "sort_key=block.sort_key or block.block_id,",
    "input_tokens=input_tokens,",
    "tokenLimit: number;",
    "  apiKey: process.env.API_KEY,",
    'token = f"tok_{uuid.uuid4().hex[:16]}"',
    'token_type = "Bearer"',
    'label_tokens: "short"',
)

_LITERAL_SECRETS = (
    ('password = "Xk9$mP2vLq8"', "Xk9$mP2vLq8"),
    ('DB_PASSWORD = "hunter2hunter2"', "hunter2hunter2"),
    ('API_KEY = "a8f5f167f44f4964e6c998dee827110c"', "a8f5f167f44f4964e6c998dee827110c"),
    ("const apiKey = 'AbCdEf123456GhIjKl';", "AbCdEf123456GhIjKl"),
    ('cfg = {"password": "p4ssw0rdValue1"}', "p4ssw0rdValue1"),
    ('client_secret="Zm9vYmFyYmF6cXV4MTIzNDU2"', "Zm9vYmFyYmF6cXV4MTIzNDU2"),
    ('headers = {"x-api-key": "k3yValue9876543210"}', "k3yValue9876543210"),
)


@pytest.mark.parametrize("line", _CODE_LINES)
def test_code_that_only_names_a_credential_stays_readable(line: str) -> None:
    assert redact_sensitive_text(line, source_code=True) == line


@pytest.mark.parametrize(("line", "secret"), _LITERAL_SECRETS)
def test_a_credential_string_literal_is_still_masked(line: str, secret: str) -> None:
    assert secret not in redact_sensitive_text(line, source_code=True)


@pytest.mark.parametrize("line", _CODE_LINES[:8])
def test_full_mode_is_unchanged(line: str) -> None:
    assert redact_sensitive_text(line) != line


@pytest.mark.parametrize(
    ("line", "secret"),
    [
        ("# leaked: sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"),
        ("# remote https://deploy:s3cr3tValue99@git.example.com/org/repo.git", "s3cr3tValue99"),
        ("# eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.c2lnbmF0dXJlMTIzNDU2", "c2lnbmF0dXJlMTIzNDU2"),
    ],
)
def test_value_shape_passes_run_on_every_line(line: str, secret: str) -> None:
    assert secret not in redact_sensitive_text(line, source_code=True)


def test_only_the_literal_line_of_a_mixed_file_is_masked() -> None:
    text = "\n".join(
        ["class Settings:", "    password: str", '    default_password = "Xk9$mP2vLq8"', "    total_tokens = 0"]
    )
    lines = redact_sensitive_text(text, source_code=True).split("\n")
    assert lines[1] == "    password: str"
    assert "Xk9$mP2vLq8" not in lines[2]
    assert lines[3] == "    total_tokens = 0"


def test_line_structure_and_line_endings_are_kept() -> None:
    text = "a = 1\r\ntotal_tokens = 0\r\n\r\nb = 2\n"
    assert redact_sensitive_text(text, source_code=True) == text
