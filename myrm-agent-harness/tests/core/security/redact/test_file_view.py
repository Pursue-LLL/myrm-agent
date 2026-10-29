"""redact_file_text redacts a file's text by the type of the file: source files in source mode, every other file in full."""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.redact import redact_file_text

_CODE = "total_api_tokens = 0\npassword: str\n"
_LITERAL = 'DEFAULT_PASSWORD = "Xk9$mP2vLq8"\n'
_ASSIGNMENTS = "total_api_tokens = 0\nDB_PASSWORD=hunter2\n"


@pytest.mark.parametrize("path", ["src/a.py", "src/a.PY", "ui/a.tsx", "pkg/main.go", "/abs/lib.rs", "C:\\src\\a.py"])
def test_source_files_keep_credential_named_code_readable(path: str) -> None:
    assert redact_file_text(path, _CODE) == _CODE
    assert "Xk9$mP2vLq8" not in redact_file_text(path, _LITERAL)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "config/.env.production",
        "app.yaml",
        "data.json",
        "pyproject.toml",
        "run.sh",
        "notes.md",
        "Makefile",
        "LICENSE",
    ],
)
def test_every_other_file_is_redacted_in_full(path: str) -> None:
    out = redact_file_text(path, _ASSIGNMENTS)
    assert "hunter2" not in out
    assert "total_api_tokens=***" in out
