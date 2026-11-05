"""The URL arguments of the network tools: one definition of which arguments carry URLs.

``web_fetch_tool`` receives its pages in ``urls`` and ``browser_navigate_tool`` receives its page in ``url``, so a
judgement that reads ``url`` alone never sees a fetch. These tests pin the shared helper.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.tool_registry import url_arg_values
from myrm_agent_harness.core.security.tool_registry.url_args import URL_ARG_KEYS


def test_a_navigation_names_its_page_in_url() -> None:
    assert url_arg_values({"url": " https://example.com/a "}) == ["https://example.com/a"]


def test_a_fetch_names_its_pages_in_urls() -> None:
    assert url_arg_values({"urls": ["https://a.com", "https://b.com/x"]}) == ["https://a.com", "https://b.com/x"]


def test_urls_sent_as_json_array_text_are_read_as_the_array() -> None:
    """The tool call can reach the approval step before its array argument is parsed."""
    assert url_arg_values({"urls": ' ["https://a.com", "https://b.com"] '}) == ["https://a.com", "https://b.com"]


def test_every_url_of_the_call_is_listed_url_first() -> None:
    args: dict[str, object] = {"urls": ["https://b.com"], "url": "https://a.com"}
    assert url_arg_values(args) == ["https://a.com", "https://b.com"]


def test_blank_and_non_string_items_are_ignored() -> None:
    args: dict[str, object] = {"urls": ["", "  ", 3, None, "https://ok.com"], "url": None}
    assert url_arg_values(args) == ["https://ok.com"]


def test_arguments_that_are_not_urls_name_no_url() -> None:
    args: dict[str, object] = {"query": "https://example.com", "reason": "open https://example.com", "mode": "all"}
    assert url_arg_values(args) == []


@pytest.mark.parametrize("value", [None, 7, 1.5, True, {"a": 1}])
@pytest.mark.parametrize("key", URL_ARG_KEYS)
def test_a_value_that_is_not_text_or_a_list_names_no_url(key: str, value: object) -> None:
    assert url_arg_values({key: value}) == []


def test_pathologically_nested_text_does_not_crash() -> None:
    text = "[" * 100_000
    assert url_arg_values({"urls": text}) == [text]
