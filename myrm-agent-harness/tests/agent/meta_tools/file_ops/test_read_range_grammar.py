"""A path argument's ``:START-END`` range has one grammar: the file tools parse it and the verdict strips it with it.

A colon is part of a file name as well (a Windows drive letter, ``notes:v2.md``), so classifying, guarding and wording
a path before it is opened must name the file the reader opens, as ``parse_path_with_range`` does, and the permission
verdict must judge that same file rather than another spelling of it.
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
from myrm_agent_harness.agent.meta_tools.file_ops.utils.file_utils import parse_path_with_range
from myrm_agent_harness.core.security.tool_registry import host_file_paths, strip_read_range

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
    # The edges of the grammar, where a looser pattern names another file than the reader opens: a range needs a file
    # name before it, the file name never spans a line break, and a line break after the range is not part of the file.
    (":1-5", ":1-5"),
    ("a\n:1-5", "a\n:1-5"),
    ("a.py:1-5\n", "a.py"),
]


@pytest.mark.parametrize(("argument", "file_path"), _ARGUMENT_AND_FILE)
def test_only_the_line_range_is_cut(argument: str, file_path: str) -> None:
    assert strip_read_range(argument) == file_path


@pytest.mark.parametrize(("argument", "_file_path"), _ARGUMENT_AND_FILE)
def test_the_file_named_is_the_one_the_reader_opens(argument: str, _file_path: str) -> None:
    assert strip_read_range(argument) == parse_path_with_range(argument)[0]


def test_stripping_the_range_validates_nothing() -> None:
    assert strip_read_range("a.py:50-10") == "a.py"
    with pytest.raises(ValueError, match="cannot be less than start line"):
        parse_path_with_range("a.py:50-10")


def test_a_vault_pointer_loses_its_range(tmp_path: Path) -> None:
    pointer = ArtifactVault(str(tmp_path)).put("x", "a.txt")

    assert strip_read_range(f"{pointer}:2-4") == pointer


@pytest.mark.parametrize("argument", ["C:/docs/plan.docx", r"C:\docs\plan.docx:1-"])
def test_a_drive_path_is_classified_by_its_extension(argument: str) -> None:
    assert is_document_path(strip_read_range(argument))


def test_a_drive_path_gets_its_outline() -> None:
    assert "Plan" in extract_file_outline("# Plan\n\ntext\n", "C:/proj/README.md")
    assert "build" in extract_truncated_outline("def build():\n    pass\n", r"C:\proj\mod.py", next_offset=1)


@pytest.mark.parametrize(
    "argument",
    [
        # A file named after its range has no name before the colon: stripping it to nothing left the verdict no path.
        ":1-5",
        "a\n:1-5",
    ],
)
def test_the_verdict_judges_the_file_the_reader_opens(argument: str) -> None:
    opened, _ = parse_path_with_range(argument)

    assert opened in host_file_paths({"path": argument})
