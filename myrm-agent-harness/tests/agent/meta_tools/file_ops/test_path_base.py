"""``path_base``: the file path of a path argument; only a trailing ``:START-END`` is cut from it.

A colon is part of a file name as well (a Windows drive letter, ``notes:v2.md``), so classifying, guarding and wording
a path before it is opened must name the file the reader opens, as ``parse_path_with_range`` does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.outline import (
    extract_file_outline,
    extract_truncated_outline,
)
from myrm_agent_harness.agent.meta_tools.file_ops.utils.document_reader import is_document_path
from myrm_agent_harness.agent.meta_tools.file_ops.utils.file_utils import parse_path_with_range, path_base

_ARGUMENT_AND_FILE = [
    ("src/a.py", "src/a.py"),
    ("src/a.py:1-50", "src/a.py"),
    ("src/a.py:100-", "src/a.py"),
    ("C:/proj/big.log", "C:/proj/big.log"),
    ("C:/proj/big.log:5-9", "C:/proj/big.log"),
    (r"D:\proj\notes.md", r"D:\proj\notes.md"),
    (r"D:\proj\notes.md:3-", r"D:\proj\notes.md"),
    ("notes:v2.md", "notes:v2.md"),
    ("notes:v2.md:92-", "notes:v2.md"),
    ("dir:name/a.txt:3-9", "dir:name/a.txt"),
    # A bare number is not a range: the reader opens a file of that name.
    ("src/a.py:10", "src/a.py:10"),
    ("@file_001:1-50", "@file_001"),
    ("/mcp/gmail/send_email.md", "/mcp/gmail/send_email.md"),
]


@pytest.mark.parametrize(("argument", "file_path"), _ARGUMENT_AND_FILE)
def test_path_base_cuts_only_the_line_range(argument: str, file_path: str) -> None:
    assert path_base(argument) == file_path


@pytest.mark.parametrize(("argument", "_file_path"), _ARGUMENT_AND_FILE)
def test_path_base_names_the_file_the_reader_opens(argument: str, _file_path: str) -> None:
    assert path_base(argument) == parse_path_with_range(argument)[0]


def test_path_base_validates_nothing() -> None:
    assert path_base("a.py:50-10") == "a.py"
    with pytest.raises(ValueError, match="cannot be less than start line"):
        parse_path_with_range("a.py:50-10")


def test_a_vault_pointer_loses_its_range(tmp_path: Path) -> None:
    pointer = ArtifactVault(str(tmp_path)).put("x", "a.txt")

    assert path_base(f"{pointer}:2-4") == pointer


@pytest.mark.parametrize("argument", ["C:/docs/plan.docx", r"C:\docs\plan.docx:1-"])
def test_a_drive_path_is_classified_by_its_extension(argument: str) -> None:
    assert is_document_path(path_base(argument))


def test_a_drive_path_gets_its_outline() -> None:
    assert "Plan" in extract_file_outline("# Plan\n\ntext\n", "C:/proj/README.md")
    assert "build" in extract_truncated_outline("def build():\n    pass\n", r"C:\proj\mod.py", next_offset=1)
