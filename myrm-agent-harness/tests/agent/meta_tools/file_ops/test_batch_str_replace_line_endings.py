"""The batch str-replace engine matches on LF text and writes the file's own line endings back.

A model sends its edits with ``\\n`` whatever the file uses. On CRLF content a multi-line ``old_str`` found no exact
match, and the fuzzy strategies, which join the lines they match with ``\\n``, matched text the content did not hold:
the edit reported success and changed nothing.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.core.batch_str_replace import (
    apply_batch_str_replace,
    compute_batch_edit_line_range,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import StrReplaceEdit

_CRLF = "def a():\r\n    return 1\r\n\r\ndef b():\r\n    return 2\r\n"
_EDITED = "def a():\r\n    return 10\r\n\r\ndef b():\r\n    return 2\r\n"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("return 1", "return 10"),
        ("def a():\n    return 1\n", "def a():\n    return 10\n"),
        ("def a():\n    return 1", "def a():\n    return 10"),
        ("    return 1\n\ndef b():", "    return 10\n\ndef b():"),
        ("def a():\r\n    return 1\r\n", "def a():\r\n    return 10\r\n"),
    ],
    ids=["one_line", "two_lines_and_newline", "two_lines", "across_a_blank_line", "written_with_crlf"],
)
def test_an_edit_applies_to_crlf_content_and_every_line_stays_crlf(old: str, new: str) -> None:
    result, _ = apply_batch_str_replace(_CRLF, (StrReplaceEdit(old_str=old, new_str=new),))

    assert result == _EDITED


def test_every_edit_of_a_batch_applies_to_crlf_content() -> None:
    edits = (
        StrReplaceEdit(old_str="def a():\n    return 1", new_str="def a():\n    return 10"),
        StrReplaceEdit(old_str="def b():\n    return 2", new_str="def b():\n    return 20"),
    )

    result, _ = apply_batch_str_replace(_CRLF, edits)

    assert result == "def a():\r\n    return 10\r\n\r\ndef b():\r\n    return 20\r\n"


def test_overlapping_multi_line_edits_are_rejected_on_crlf_content() -> None:
    edits = (
        StrReplaceEdit(old_str="def a():\n    return 1", new_str="x"),
        StrReplaceEdit(old_str="    return 1\n\ndef b():", new_str="y"),
    )

    with pytest.raises(ValueError, match="overlap"):
        apply_batch_str_replace(_CRLF, edits)


def test_a_text_that_is_not_in_a_crlf_file_is_reported_not_found() -> None:
    with pytest.raises(ValueError, match="text not found"):
        apply_batch_str_replace(_CRLF, (StrReplaceEdit(old_str="def c():\n    return 3", new_str="x"),))


def test_the_edit_line_range_of_crlf_content_is_the_lines_the_edit_names() -> None:
    edit = StrReplaceEdit(old_str="    return 1\n\ndef b():", new_str="")

    assert compute_batch_edit_line_range(_CRLF, (edit,)) == (2, 4)


def test_an_lf_file_stays_lf() -> None:
    lf = _CRLF.replace("\r\n", "\n")

    result, _ = apply_batch_str_replace(
        lf, (StrReplaceEdit(old_str="def a():\n    return 1", new_str="def a():\n    return 10"),)
    )

    assert result == _EDITED.replace("\r\n", "\n")


def test_a_file_that_separates_its_lines_with_lone_cr_is_matched_and_written_as_it_is() -> None:
    result, _ = apply_batch_str_replace("a\rb\rc", (StrReplaceEdit(old_str="b", new_str="B"),))

    assert result == "a\rB\rc"
