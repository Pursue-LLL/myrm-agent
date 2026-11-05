"""Trailing-space normalisation of the HTML-to-Markdown converter."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.web_fetch.processing.html_to_markdown import CustomHTML2Text

_RUN = 750_000


def _convert(html: str) -> str:
    return CustomHTML2Text().handle(html)


def test_hard_break_leaves_no_trailing_spaces() -> None:
    assert _convert("<p>a<br>b</p>") == "a\nb\n"


def test_spaces_before_a_newline_are_removed_inside_code_blocks_too() -> None:
    assert _convert("<pre>a   \nb</pre>") == "```\na\nb\n```\n"


@pytest.mark.timeout(10)
def test_page_sized_run_of_spaces_without_a_newline_is_kept() -> None:
    assert _convert("<pre>" + " " * _RUN + "x</pre>") == "```\n" + " " * _RUN + "x\n```\n"


@pytest.mark.timeout(10)
def test_page_sized_run_of_spaces_before_a_newline_is_removed() -> None:
    assert _convert("<pre>" + " " * _RUN + "\nx</pre>") == "```\n\nx\n```\n"
