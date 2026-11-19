"""A file's text is redacted by the type of the file: source files in source mode, every other file in full.

The text a reader extracts from a document is redacted by the type of the document: a notebook's cells as source
code, everything else in full.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.redact import redact_extracted_text, redact_file_text

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


def test_the_raw_lines_of_a_notebook_are_json_and_redacted_in_full() -> None:
    # grep shows a notebook as the JSON it is: a bare assignment in an output cell is masked as in any JSON file.
    raw = json.dumps({"cells": [{"outputs": [{"text": ["DB_PASSWORD=hunter2\n"]}]}]}, indent=1)

    assert "hunter2" not in redact_file_text("lab/analysis.ipynb", raw)


@pytest.mark.parametrize("path", ["lab/analysis.ipynb", "lab/Analysis.IPYNB"])
def test_the_code_extracted_from_a_notebook_stays_readable_and_a_literal_secret_does_not(path: str) -> None:
    assert redact_extracted_text(path, _CODE) == _CODE
    assert "Xk9$mP2vLq8" not in redact_extracted_text(path, _LITERAL)


@pytest.mark.parametrize(
    "path", ["report.docx", "sheet.xlsx", "deck.pptx", "paper.pdf", "pic.png", "clip.mp4", "notes"]
)
def test_the_text_extracted_from_any_other_file_is_redacted_in_full(path: str) -> None:
    out = redact_extracted_text(path, _ASSIGNMENTS)

    assert "hunter2" not in out
    assert "total_api_tokens=***" in out
