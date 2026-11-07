"""Outbound URL syntax check: what every outbound policy rejects, and the one spelling of a URL it admits.

A URL is parsed once into its canonical spelling; the host a policy judges is the host of that spelling, and the
spelling is what the client dials, so no reader of the URL can see another host than the client connects to.
"""

from __future__ import annotations

import random
from urllib.parse import urlparse

import pytest

from myrm_agent_harness.utils.url_syntax import OutboundUrl, parse_outbound_hostname, parse_outbound_url


@pytest.mark.parametrize(
    ("url", "hostname"),
    [
        ("https://example.com/path", "example.com"),
        ("http://localhost:3000/", "localhost"),  # no blocklist here: a policy that admits private hosts relies on this
        ("http://LOCALHOST./", "localhost"),  # trailing dot stripped and case folded, so blocklists match
        ("http://[::1]:8080/", "::1"),
        ("wss://stream.example.com/", "stream.example.com"),
        ("https://us%40er@example.com/a%20b?q=%41", "example.com"),  # '%' outside the host is plain URL text
        ("http://a.test:80@evil.test/", "evil.test"),  # what precedes the last '@' is credentials, never the host
        ("http://2130706433/", "127.0.0.1"),  # the address a client dials, not the digits a blocklist would read
        ("http://0x7f.1:8080/", "127.0.0.1"),
        ("http://STRAßE.example/", "xn--strae-oqa.example"),
        ("https://ＥＸＡＭＰＬＥ。com/", "example.com"),
    ],
)
def test_accepts_http_family_urls_and_returns_the_canonical_host(url: str, hostname: str) -> None:
    assert parse_outbound_hostname(url) == (hostname, "")


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        ("https://example.com/path", "https://example.com/path"),
        ("HTTP://EXAMPLE.com./a?b=1#c", "http://example.com/a?b=1#c"),
        ("https://example.com", "https://example.com"),
        ("https://example.com?x=1", "https://example.com?x=1"),
        ("https://example.com#frag", "https://example.com#frag"),
        ("https://example.com:/x", "https://example.com/x"),
        ("https://münchen.de:0443/x", "https://xn--mnchen-3ya.de:443/x"),
        ("http://2130706433:8080/", "http://127.0.0.1:8080/"),
        ("http://[0:0:0:0:0:0:0:1]:80/", "http://[::1]:80/"),
        ("http://user:p%40ss@EXAMPLE.com/", "http://user:p%40ss@example.com/"),
        ("WSS://Ｅxample.com/s", "wss://example.com/s"),
        ("  https://example.com/a \n", "https://example.com/a"),
        ("http://a.test/x@evil.test/", "http://a.test/x@evil.test/"),  # '@' after the authority is path text
    ],
)
def test_the_canonical_url_spells_the_host_a_client_dials(url: str, canonical: str) -> None:
    target, error = parse_outbound_url(url)

    assert error == ""
    assert target is not None
    assert target.url == canonical


@pytest.mark.parametrize(
    ("url", "error"),
    [
        ("http://evil.com\t@169.254.169.254/", "parser-confusing"),
        ("http://evil.com\\@169.254.169.254/", "parser-confusing"),
        ("http://evil.com\n.internal/", "parser-confusing"),
        ("http://127%2e0%2e0%2e1/", "percent-encoding"),  # a client decodes it and dials 127.0.0.1
        ("http://local%68ost:8080/", "percent-encoding"),
        ("http://169.254.169.%32%35%34/latest/meta-data/", "percent-encoding"),
        ("https://%65xample.com/", "percent-encoding"),
        ("file:///etc/passwd", "Blocked URL scheme: file"),
        ("ftp://example.com/", "Blocked URL scheme: ftp"),
        ("gopher://example.com/", "Blocked URL scheme: gopher"),
        ("example.com/no-scheme", "Blocked URL scheme: "),
        ("\x01http://example.com/", "Blocked URL scheme: "),
        ("ｈttp://example.com/", "Blocked URL scheme: "),
        ("http:///path", "Missing hostname"),
        ("http://:80/", "Missing hostname"),
        ("http://@/", "Missing hostname"),
        ("http:/example.com/", "Missing hostname"),
        ("http:example.com", "Missing hostname"),
    ],
)
def test_rejects_urls_a_client_and_a_parser_could_read_differently(url: str, error: str) -> None:
    hostname, message = parse_outbound_hostname(url)

    assert hostname is None
    assert error in message


@pytest.mark.parametrize(
    "url",
    [
        "http://a@b@evil.test/",
        "http://a.test:80:90/",
        "http://[::1/",
        "http://[::1]x/",
        "http://exa mple.com/",
        "http://example.com\x00/",
        "http://example.com\x01/",
        "http://example.com\x7f/",
    ],
)
def test_an_authority_that_does_not_hold_exactly_one_host_is_malformed(url: str) -> None:
    assert parse_outbound_url(url) == (None, "Malformed URL")


@pytest.mark.parametrize("tail", ["/a b", "?q=a b", "/?q=a b", "/#a b", "/a\x01b", "/a\x7fb", "/é", "/%zz"])
def test_the_text_after_the_authority_is_kept_as_written(tail: str) -> None:
    """Only the authority names the host; spaces, control characters and stray escapes after it are the caller's text."""
    assert parse_outbound_url(f"https://example.com{tail}") == (
        OutboundUrl(f"https://example.com{tail}", "example.com"),
        "",
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://a..b/",
        "http://256.1.1.1/",
        "http://1.2.3.4.5/",
        "http://[fe80::1%25en0]:8080/",  # a zone id names an interface; no outbound request carries one
        "http://[::1%en0]/",
        "http://[1:2]/",
        "http://" + "a" * 64 + ".com/",
    ],
)
def test_a_host_with_no_canonical_spelling_is_refused(url: str) -> None:
    assert parse_outbound_url(url) == (None, "Invalid hostname")


@pytest.mark.parametrize(
    "port",
    ["80x", "99999", "65536", "-1", "+80", "8_0", "%38%30", "١٢٣", "²", "123456", "9" * 5000],
)
def test_a_port_that_is_not_one_to_five_ascii_digits_within_range_is_refused(port: str) -> None:
    """``int()`` reads ``١٢٣`` as 123 and ``+80`` as 80; a client reads neither as a port."""
    assert parse_outbound_url(f"http://a.test:{port}/") == (None, "Invalid port")


def test_a_port_is_its_number_without_leading_zeros_and_zero_is_a_port() -> None:
    assert parse_outbound_url("http://a.test:0080/") == (OutboundUrl("http://a.test:80/", "a.test"), "")
    assert parse_outbound_url("http://a.test:65535/")[0] == OutboundUrl("http://a.test:65535/", "a.test")
    assert parse_outbound_url("http://a.test:0/")[0] == OutboundUrl("http://a.test:0/", "a.test")


_HOSTS = [
    "Example.COM",
    "münchen.de",
    "ＥＸＡＭＰＬＥ。com",
    "2130706433",
    "0x7f.1",
    "[::1]",
    "[0:0:0:0:0:0:0:1]",
    "a_b.test",
]
_TAILS = ["", "/", "/a/b?c=d", "?q=1", "#f", "/x@y/z", "/%41"]


def test_every_reader_of_a_canonical_url_sees_the_host_the_client_dials() -> None:
    """The stdlib parser, the engine and the blocklists read the canonical URL; they must all find its one host."""
    rng = random.Random(46)

    for _ in range(500):
        host = rng.choice(_HOSTS)
        port = rng.choice(["", ":80", ":0080", ":65535"])
        userinfo = rng.choice(["", "u@", "u:p@"])
        tail = rng.choice(_TAILS)
        url = f"{rng.choice(['http', 'HTTPS', 'ws', 'Wss'])}://{userinfo}{host}{port}{tail}"

        target, error = parse_outbound_url(url)

        assert error == "" and target is not None, url
        assert urlparse(target.url).hostname == target.hostname, url
        assert target.url.endswith(tail), url
        assert parse_outbound_url(target.url) == (target, ""), url
