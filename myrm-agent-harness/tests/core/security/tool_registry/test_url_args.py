"""The URL arguments of the network tools: one definition of which arguments carry URLs.

``web_fetch_tool`` receives its pages in ``urls`` and ``browser_navigate_tool`` receives its page in ``url``, so a
judgement that reads ``url`` alone never sees a fetch. These tests pin the shared helpers: the URLs a call names and the
hosts those URLs name.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.tool_registry import url_arg_hosts, url_arg_values, url_host
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


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("http://192.168.1.1/admin", "192.168.1.1"),
        ("https://API.Example.com:8443/v1?q=1", "api.example.com"),
        ("https://user:pw@example.com/x", "example.com"),
        ("localhost:3000/api", "localhost"),
        ("LOCALHOST:3000", "localhost"),
        ("Example.com/page", "example.com"),
        ("https://example.com./x", "example.com"),
        ("Example.COM.", "example.com"),
    ],
)
def test_the_host_is_lowercase_without_scheme_port_path_or_trailing_dot(url: str, host: str) -> None:
    assert url_host(url) == host


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("http://attacker.test\\@good.test/x?d=1", "attacker.test"),
        ("https://evil.test\\.good.test/x", "evil.test"),
        ("https://good.test\\path", "good.test"),
        ("https://good.test/a\\b@evil.test/", "good.test"),
    ],
)
def test_a_backslash_ends_the_authority_as_a_browser_reads_it(url: str, host: str) -> None:
    assert url_host(url) == host


@pytest.mark.parametrize("url", ["://bad", "file:///etc/passwd", "http://[::1", "http://./"])
def test_a_url_without_a_host_stands_for_itself(url: str) -> None:
    assert url_host(url) == url


def test_every_url_of_the_call_gives_its_host_once_in_order() -> None:
    urls = ["https://b.test/1", "https://a.test", "https://B.test./2", "a.test:8080"]

    assert url_arg_hosts({"urls": urls}) == ("b.test", "a.test")


def test_the_hosts_of_url_and_urls_are_listed_url_first() -> None:
    assert url_arg_hosts({"urls": ["https://b.test"], "url": "https://a.test"}) == ("a.test", "b.test")


def test_json_text_of_a_list_names_the_hosts_of_the_list() -> None:
    assert url_arg_hosts({"urls": json.dumps(["https://a.test", "https://b.test"])}) == ("a.test", "b.test")


def test_a_single_url_string_names_one_host() -> None:
    assert url_arg_hosts({"urls": "https://a.test/page"}) == ("a.test",)


def test_blank_and_non_string_values_name_no_host() -> None:
    assert url_arg_hosts({"urls": ["", "  ", 3, None], "url": None, "reason": "https://a.test"}) == ()
