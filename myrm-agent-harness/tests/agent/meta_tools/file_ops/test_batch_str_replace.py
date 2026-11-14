"""Tests for batch_str_replace core."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.core.batch_str_replace import (
    MAX_EDITS_PER_CALL,
    apply_batch_str_replace,
    check_non_overlapping_edits,
    compute_batch_edit_line_range,
    validate_edits_batch,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import (
    StrReplaceEdit,
)


def test_apply_batch_two_edits_sequential() -> None:
    content = "alpha\nbeta\ngamma"
    edits = (
        StrReplaceEdit(old_str="alpha", new_str="ALPHA"),
        StrReplaceEdit(old_str="gamma", new_str="GAMMA"),
    )
    result, strategies = apply_batch_str_replace(content, edits)
    assert result == "ALPHA\nbeta\nGAMMA"
    assert strategies == ["exact", "exact"]


def test_apply_batch_second_edit_fails_no_partial_apply_in_memory() -> None:
    content = "keep me"
    edits = (
        StrReplaceEdit(old_str="keep", new_str="changed"),
        StrReplaceEdit(old_str="missing", new_str="x"),
    )
    with pytest.raises(ValueError, match="Edit 2"):
        apply_batch_str_replace(content, edits)


def test_overlap_rejected_on_original_content() -> None:
    content = "abcdef"
    edits = (
        StrReplaceEdit(old_str="abc", new_str="1"),
        StrReplaceEdit(old_str="bcd", new_str="2"),
    )
    with pytest.raises(ValueError, match="overlap"):
        check_non_overlapping_edits(content, edits)


def test_max_edits_limit() -> None:
    edits = tuple(StrReplaceEdit(old_str="a", new_str="b") for _ in range(MAX_EDITS_PER_CALL + 1))
    with pytest.raises(ValueError, match=str(MAX_EDITS_PER_CALL)):
        validate_edits_batch(edits)


def test_validate_empty_old_str() -> None:
    with pytest.raises(ValueError, match="old_str cannot be empty"):
        validate_edits_batch((StrReplaceEdit(old_str="", new_str="x"),))


def test_validate_empty_edits() -> None:
    with pytest.raises(ValueError, match="non-empty 'edits'"):
        validate_edits_batch(())


def test_find_exclusive_span_multiple_matches() -> None:
    with pytest.raises(ValueError, match="Found 2 matches"):
        apply_batch_str_replace("aa", (StrReplaceEdit(old_str="a", new_str="b"),))


def test_compute_batch_edit_line_range_empty() -> None:
    start, end = compute_batch_edit_line_range("a\nb\n", ())
    assert start == 1
    assert end == 3


def test_compute_batch_edit_line_range_union() -> None:
    content = "line_a\nline_b\nline_c\n"
    edits = (
        StrReplaceEdit(old_str="line_a", new_str="LINE_A"),
        StrReplaceEdit(old_str="line_c", new_str="LINE_C"),
    )
    start, end = compute_batch_edit_line_range(content, edits)
    assert start == 1
    assert end == 3


def test_apply_rejects_duplicate_after_prior_edit_expands_match() -> None:
    # Edit 2 old_str absent in original (skipped by overlap precheck); first edit creates duplicates.
    content = "MARKER bb"
    edits = (
        StrReplaceEdit(old_str="MARKER", new_str="aa"),
        StrReplaceEdit(old_str="a", new_str="x"),
    )
    with pytest.raises(ValueError, match="Edit 2: found 2 matches"):
        apply_batch_str_replace(content, edits)


def test_fuzzy_apply_success() -> None:
    from unittest.mock import MagicMock, patch

    fuzzy_result = MagicMock()
    fuzzy_result.success = True
    fuzzy_result.content = "replaced content"
    fuzzy_result.strategy = "trimmed"
    fuzzy_result.confidence = 0.95
    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.batch_str_replace.fuzzy_replace",
        return_value=fuzzy_result,
    ):
        result, strategies = apply_batch_str_replace("content", (StrReplaceEdit(old_str="missing", new_str="x"),))
    assert result == "replaced content"
    assert strategies == ["trimmed"]


def test_fuzzy_apply_with_hint() -> None:
    from unittest.mock import MagicMock, patch

    fuzzy_result = MagicMock()
    fuzzy_result.success = False
    with (
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.batch_str_replace.fuzzy_replace",
            return_value=fuzzy_result,
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.batch_str_replace.find_closest_lines",
            return_value="\nDid you mean line 2?",
        ),
        pytest.raises(ValueError, match="Did you mean"),
    ):
        apply_batch_str_replace("content", (StrReplaceEdit(old_str="missing", new_str="x"),))


def test_apply_preserves_crlf_via_line_endings() -> None:
    content = "a\r\nb\r\n"
    result, _ = apply_batch_str_replace(content, (StrReplaceEdit(old_str="b", new_str="B"),))
    assert "\r\n" in result


_LOADER = "\n".join(
    [
        "import os",
        "",
        "def load(path):",
        "    with open(path) as fh:",
        "        raw = fh.read()",
        "    data = json.loads(raw)",
        "    validate(data)",
        "    return data",
        "",
        "def save(path, data):",
        "    pass",
    ]
)


# First and last line are the file's; two of the lines in between are misremembered.
_MISREMEMBERED_LOADER = "\n".join(
    [
        "def load(path):",
        "    with open(path, encoding='utf-8') as fh:",
        "        text = fh.read()",
        "    data = json.loads(text)",
        "    validate(data)",
        "    return data",
    ]
)


def test_a_block_with_misremembered_lines_is_refused_and_the_real_lines_are_shown() -> None:
    with pytest.raises(ValueError, match="Edit 1: text not found") as exc_info:
        apply_batch_str_replace(
            _LOADER,
            (StrReplaceEdit(old_str=_MISREMEMBERED_LOADER, new_str="def load(path):\n    ..."),),
        )

    message = str(exc_info.value)
    assert "Did you mean" in message
    assert "   5|         raw = fh.read()" in message
    assert "   6|     data = json.loads(raw)" in message


def test_a_refused_block_in_a_batch_leaves_no_partial_result() -> None:
    edits = (
        StrReplaceEdit(old_str="import os", new_str="import os\nimport sys"),
        StrReplaceEdit(old_str=_MISREMEMBERED_LOADER, new_str="x"),
    )
    with pytest.raises(ValueError, match="Edit 2: text not found"):
        apply_batch_str_replace(_LOADER, edits)


def test_a_block_that_differs_only_in_indentation_still_applies() -> None:
    shifted = "def load(path):\n  with open(path) as fh:\n      raw = fh.read()\n  data = json.loads(raw)"
    result, strategies = apply_batch_str_replace(
        _LOADER,
        (StrReplaceEdit(old_str=shifted, new_str="def load(path):\n    return {}"),),
    )
    assert strategies != ["exact"]
    assert "return {}" in result
    assert "    validate(data)" in result
