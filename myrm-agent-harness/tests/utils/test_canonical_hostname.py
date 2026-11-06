"""The one spelling of a host that every outbound-URL policy judges and every outbound request dials.

Every expected value in ``_BROWSER_HOSTS`` is the hostname the WHATWG URL parser gives for the same text (Node
``new URL``), minus a single trailing dot. The shape of the table is the contract: a host is judged under the
name a client resolves, so a spelling that a client folds (full-width letters, ``0x7f.1``) can never be judged
under a different name than the one it dials.
"""

from __future__ import annotations

import ipaddress
import random
from urllib.parse import urlparse

import pytest

from myrm_agent_harness.utils import url_syntax
from myrm_agent_harness.utils.url_syntax import canonical_hostname

_UNSPECIFIED = "0.0.0.0"  # noqa: S104  # an address a host text names, not a bind

_BROWSER_HOSTS: list[tuple[str, str]] = [
    # case, one trailing dot, label characters
    ("Example.COM", "example.com"),
    ("EXAMPLE.com.", "example.com"),
    ("a_b.example.com", "a_b.example.com"),
    ("-a.example.com", "-a.example.com"),
    ("_dmarc.example.com", "_dmarc.example.com"),
    ("xn--mnchen-3ya.de", "xn--mnchen-3ya.de"),
    # UTS 46 mapping: full-width letters and digits, ideographic full stops, enclosed letters, ligatures, ignored marks
    ("ｅｘａｍｐｌｅ.ｃｏｍ", "example.com"),
    ("example。com", "example.com"),
    ("example．com", "example.com"),
    ("example｡com", "example.com"),
    ("EXAMPLE.COM。", "example.com"),
    ("ｌｏｃａｌｈｏｓｔ。", "localhost"),
    ("ⓔⓧⓐⓜⓟⓛⓔ.com", "example.com"),
    ("ﬁ.com", "fi.com"),
    ("㎒.com", "mhz.com"),
    ("exa\u00admple.com", "example.com"),
    # a Unicode label is its Punycode, after NFC composition
    ("münchen.de", "xn--mnchen-3ya.de"),
    ("MÜNCHEN.DE", "xn--mnchen-3ya.de"),
    ("mu\u0308nchen.de", "xn--mnchen-3ya.de"),
    ("日本語.jp", "xn--wgv71a119e.jp"),
    ("😀.com", "xn--e28h.com"),
    ("аррӏе.com", "xn--80ak6aa92e.com"),
    # sharp s, final sigma and the joiner keep their own names: ``str.lower()`` and IDNA 2003 would fold them
    ("straße.de", "xn--strae-oqa.de"),
    ("Straße.DE", "xn--strae-oqa.de"),
    ("STRASSE.DE", "strasse.de"),
    ("σας.gr", "xn--mxa8ab.gr"),
    ("ΣΑΣ.gr", "xn--mxa9ab.gr"),
    ("σασ.gr", "xn--mxa9ab.gr"),
    ("می\u200cخواهم.ir", "xn--mgbn2ecje63gr19l.ir"),
    ("ß", "xn--zca"),
    ("ς", "xn--3xa"),
    ("Σ", "xn--4xa"),
    # a host whose last label is a number is the dotted address a client dials
    ("2130706433", "127.0.0.1"),
    ("0x7f000001", "127.0.0.1"),
    ("0x7f.1", "127.0.0.1"),
    ("0X7F.1", "127.0.0.1"),
    ("0177.0.0.1", "127.0.0.1"),
    ("00177.1", "127.0.0.1"),
    ("127.1", "127.0.0.1"),
    ("127.0.1", "127.0.0.1"),
    ("0x7f.0.0.0x1", "127.0.0.1"),
    ("0xa9.0xfe.0xa9.0xfe", "169.254.169.254"),
    ("4294967295", "255.255.255.255"),
    ("1.2.3", "1.2.0.3"),
    ("1.65535", "1.0.255.255"),
    ("1.16777215", "1.255.255.255"),
    ("1.2.3.4.", "1.2.3.4"),
    ("0", _UNSPECIFIED),
    ("00", _UNSPECIFIED),
    ("0x", _UNSPECIFIED),
    ("①②⑦.0.0.1", "127.0.0.1"),
    ("１２７。０。０。１", "127.0.0.1"),
    # a name whose last label is not a number stays a name
    ("a.1e", "a.1e"),
    ("0x1g", "0x1g"),
    ("①②⑦.com", "127.com"),
    # an IPv6 literal is its compressed form, without brackets
    ("::1", "::1"),
    ("0:0:0:0:0:0:0:1", "::1"),
    ("2001:0DB8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
]

# A browser refuses each of these, so no client dials them either.
_BROWSER_REFUSED = [
    "4294967296",
    "0x100000000",
    "256.1.1.1",
    "256.0.0.1",
    "1.16777216",
    "1.2.3.4.5",
    "08",
    "example.123",
    "a b.com",
    "a%b.com",
    "a<b.com",
    "a>b.com",
    "a^b.com",
    "a|b.com",
    "a[b.com",
    "a]b.com",
    "ex\u0000ample.com",
    "\u202e.com",
    "evil.com\u2025",
    "evil.com\ufe52",
    "",
]

# A browser passes these to the resolver, which finds no such name; refusing them here costs nothing.
_NO_DNS_NAME = ["a..b", ".", "..", ".example.com", "A" * 64 + ".com", "\ufffd.com", "a\u0080b.é"]

_ALPHABET = [
    *"abcXYZ019-_.ßςΣéüİıǅǰΐ",
    "\u0308",
    "\u200c",
    "\u200d",
    "\u00ad",
    "。",
    "．",
    "｡",
    "ｅ",
    "Ａ",
    "①",
    "٣",
    "0x",
    "xn--",
]


@pytest.mark.parametrize(("text", "hostname"), _BROWSER_HOSTS)
def test_a_host_reads_as_the_hostname_a_browser_dials(text: str, hostname: str) -> None:
    assert canonical_hostname(text) == hostname


@pytest.mark.parametrize("text", _BROWSER_REFUSED)
def test_a_text_a_browser_refuses_names_no_host(text: str) -> None:
    assert canonical_hostname(text) is None


@pytest.mark.parametrize("text", _NO_DNS_NAME)
def test_a_name_with_an_empty_or_oversized_label_names_no_host(text: str) -> None:
    assert canonical_hostname(text) is None


@pytest.mark.parametrize(
    ("text", "hostname"),
    [
        ("::ffff:7f00:1", "::ffff:127.0.0.1"),
        ("::FFFF:127.0.0.1", "::ffff:127.0.0.1"),
        ("64:ff9b::7f00:1", "64:ff9b::7f00:1"),
    ],
)
def test_an_ipv6_literal_names_the_address_it_holds(text: str, hostname: str) -> None:
    """Python compresses an IPv4-mapped address with its dotted tail; the address is the one a client dials."""
    assert canonical_hostname(text) == hostname
    assert ipaddress.IPv6Address(hostname) == ipaddress.IPv6Address(text)


@pytest.mark.parametrize("text", ["fe80::1%en0", "fe80::1%25en0", "::1::2", "1:2:3:4:5:6:7:8:9", "::g", "1:2"])
def test_an_ipv6_text_that_is_no_plain_address_names_no_host(text: str) -> None:
    """A zone id names an interface, not a host; no outbound request carries one."""
    assert canonical_hostname(text) is None


def test_a_name_of_253_characters_is_a_host_and_one_more_is_not() -> None:
    longest = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61])

    assert len(longest) == 253
    assert canonical_hostname(longest) == longest
    assert canonical_hostname(longest + "d") is None
    assert canonical_hostname(longest + ".") == longest


def test_text_longer_than_a_dns_name_never_enters_the_cache() -> None:
    cached = url_syntax._canonical_short_hostname.cache_info().currsize

    assert canonical_hostname("a" * 300 + ".com") is None
    assert url_syntax._canonical_short_hostname.cache_info().currsize == cached


def _spell_ipv4(address: int, rng: random.Random) -> str:
    """A legacy spelling of *address*: one to four parts, each in decimal, hexadecimal or octal."""
    count = rng.randint(1, 4)
    parts = [(address >> shift) & 0xFF for shift in (24, 16, 8)[: count - 1]]
    parts.append(address & ((1 << (8 * (5 - count))) - 1))
    spelled = []
    for part in parts:
        radix = rng.choice("dxXo")
        if radix == "d":
            spelled.append(str(part))
        elif radix == "o":
            spelled.append(f"0{part:o}")
        else:
            digits = f"{part:x}" if rng.random() < 0.5 else f"{part:X}"
            spelled.append(f"0{radix}{digits}")
    return ".".join(spelled)


def test_every_legacy_spelling_of_an_address_is_its_dotted_decimal() -> None:
    rng = random.Random(46)
    edges = [0, 1, 255, 256, 65535, 65536, 16777215, 16777216, 2**32 - 1, 0x7F000001, 0xA9FEA9FE]

    for address in edges + [rng.randrange(2**32) for _ in range(3000)]:
        text = _spell_ipv4(address, rng)
        assert canonical_hostname(text) == str(ipaddress.IPv4Address(address)), text


def test_a_canonical_host_is_ascii_lowercase_a_fixed_point_and_read_the_same_by_the_stdlib() -> None:
    rng = random.Random(46)
    named = 0

    for _ in range(6000):
        text = "".join(rng.choice(_ALPHABET) for _ in range(rng.randint(1, 8)))
        host = canonical_hostname(text)
        if host is None:
            continue
        named += 1
        assert host.isascii(), text
        assert host == host.lower(), text
        assert canonical_hostname(host) == host, text
        assert urlparse(f"http://{host}/").hostname == host, text

    assert named > 3000  # the alphabet must keep producing hosts, or the loop above checks nothing
