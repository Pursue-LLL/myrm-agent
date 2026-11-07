"""Canonical form and syntax check for outbound URLs, independent of any hostname blocklist.

[INPUT]
- idna::uts46_remap (POS: UTS 46 name mapping, the normalization a browser applies to a host before it dials)

[OUTPUT]
- SSRF_ALLOWED_SCHEMES: schemes an outbound request may use
- canonical_hostname(): the one ASCII spelling of a host name or IP literal, or None when it is not a host
- OutboundUrl / parse_outbound_url(): (canonical URL and host, "") or (None, error)
- parse_outbound_hostname(): (canonical hostname, "") or (None, error)

[POS]
Shared by every outbound-URL policy, including the ones that admit private hosts (local mode) and
therefore have no hostname blocklist. A URL is parsed once into its canonical spelling and judged and
dialed in that spelling, so every reader of one URL sees the host the client connects to; a URL that has
no canonical spelling is refused instead of being read two ways.
"""

from __future__ import annotations

import ipaddress
import re
from functools import lru_cache
from typing import NamedTuple

SSRF_ALLOWED_SCHEMES = frozenset({"http", "https", "ws", "wss"})

# Parser-confusing characters that cause urlparse/HTTP client divergence.
# Attackers inject these to bypass hostname extraction (CVE-class SSRF bypass).
_PARSER_CONFUSING = re.compile(r"[\\\t\n\r]")
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
_AUTHORITY_END = re.compile(r"[/?#]")
_AUTHORITY_FORBIDDEN = re.compile(r"[\x00-\x20\x7f]")
_LABEL = re.compile(r"[a-z0-9_-]{1,63}")
# A DNS name is at most 253 characters. Longer text is never a host and never reaches the UTS 46 mapping, whose cost
# grows with the text, nor the host cache, where distinct oversized strings would be kept alive.
_MAX_HOST_LENGTH = 253
_MAX_PORT_DIGITS = 5
_MAX_PORT = 65535
_RADIX_DIGITS = {8: "01234567", 10: "0123456789", 16: "0123456789abcdef"}


class OutboundUrl(NamedTuple):
    """An outbound URL in canonical spelling, with the host it names (an IPv6 literal without brackets)."""

    url: str
    hostname: str


def _ipv4_part(part: str) -> int | None:
    """One dot-separated part of a legacy IPv4 host: decimal, ``0x`` hexadecimal or ``0`` octal."""
    radix = 10
    digits = part.lower()
    if digits.startswith("0x"):
        digits, radix = digits[2:], 16
    elif len(digits) > 1 and digits.startswith("0"):
        digits, radix = digits[1:], 8
    if not digits:
        return 0 if radix == 16 else None
    if any(char not in _RADIX_DIGITS[radix] for char in digits):
        return None
    return int(digits, radix)


def _ends_in_number(name: str) -> bool:
    """Whether a client reads *name* as an IPv4 address: its last label is a number, valid or not (``08``)."""
    last = name.rsplit(".", 1)[-1]
    return (last.isascii() and last.isdigit()) or _ipv4_part(last) is not None


def _dotted_ipv4(name: str) -> str | None:
    """The dotted-decimal address a host such as ``2130706433`` or ``0x7f.1`` names, as a client dials it."""
    parts = name.split(".")
    numbers = [_ipv4_part(part) for part in parts]
    if len(parts) > 4 or any(number is None for number in numbers):
        return None
    *leading, last = (number for number in numbers if number is not None)
    if any(number > 255 for number in leading) or last >= 256 ** (5 - len(parts)):
        return None
    address = last + sum(number << (8 * (3 - index)) for index, number in enumerate(leading))
    return str(ipaddress.IPv4Address(address))


def _fold(name: str) -> str | None:
    """UTS 46 mapped *name* with every non-ASCII label as Punycode; None when the mapping rejects it."""
    import idna  # first needed by a non-ASCII name; the hosts of nearly every call are ASCII

    try:
        labels = idna.uts46_remap(name, std3_rules=False, transitional=False).split(".")
        return ".".join(
            label if label.isascii() else f"xn--{label.encode('punycode').decode('ascii')}" for label in labels
        )
    except UnicodeError:
        return None


@lru_cache(maxsize=2048)
def _canonical_short_hostname(text: str) -> str | None:
    if ":" in text:
        try:
            return ipaddress.IPv6Address(text).compressed if "%" not in text else None
        except ValueError:
            return None
    name = text.lower() if text.isascii() else _fold(text)
    if name is None:
        return None
    name = name.removesuffix(".")
    if len(name) > _MAX_HOST_LENGTH or not all(_LABEL.fullmatch(label) for label in name.split(".")):
        return None
    return _dotted_ipv4(name) if _ends_in_number(name) else name


def canonical_hostname(text: str) -> str | None:
    """The one ASCII spelling of the host *text* names: what a browser dials, or None when *text* is no host.

    Letters are lowercased and non-ASCII labels become Punycode (UTS 46: full-width letters and ideographic full
    stops become their plain forms, ``ß`` and ``ς`` stay themselves), one trailing dot is dropped, a legacy numeric
    IPv4 host becomes dotted decimal and an IPv6 literal gets its compressed form, without brackets.
    """
    return _canonical_short_hostname(text) if len(text) <= _MAX_HOST_LENGTH + 1 else None


def _split_authority(authority: str) -> tuple[str, str, str] | None:
    """(userinfo with its ``@``, host text, port text), or None when the authority does not hold one host."""
    if _AUTHORITY_FORBIDDEN.search(authority) or authority.count("@") > 1:
        return None
    userinfo, at, host_port = authority.rpartition("@")
    if host_port.startswith("["):
        host, bracket, after = host_port[1:].partition("]")
        if not bracket or (after and not after.startswith(":")):
            return None
        return userinfo + at, host, after[1:]
    host, _, port = host_port.partition(":")
    return (userinfo + at, host, port) if ":" not in port else None


def parse_outbound_url(url: str) -> tuple[OutboundUrl | None, str]:
    """Canonical spelling of an outbound URL. Returns (OutboundUrl, "") or (None, error)."""
    url = url.strip()
    # e.g. http://evil.com\t@169.254.169.254/ — tab makes urlparse extract the wrong hostname.
    if _PARSER_CONFUSING.search(url):
        return None, "URL contains parser-confusing characters"

    scheme_match = _SCHEME.match(url)
    scheme = scheme_match.group(1).lower() if scheme_match else ""
    if scheme not in SSRF_ALLOWED_SCHEMES:
        return None, f"Blocked URL scheme: {scheme}"
    rest = url[scheme_match.end() :] if scheme_match else ""
    if not rest.startswith("//"):
        return None, "Missing hostname"
    rest = rest[2:]
    boundary = _AUTHORITY_END.search(rest)
    end = boundary.start() if boundary else len(rest)
    parts = _split_authority(rest[:end])
    if parts is None:
        return None, "Malformed URL"
    userinfo, host, port = parts

    # An HTTP client percent-decodes a host before dialing it (127%2e0%2e0%2e1 reaches 127.0.0.1) while the
    # classifiers read the raw text.
    if "%" in host and ":" not in host:
        return None, "Hostname contains percent-encoding"
    if not host:
        return None, "Missing hostname"
    hostname = canonical_hostname(host)
    if hostname is None:
        return None, "Invalid hostname"
    if port and not (port.isascii() and port.isdigit() and len(port) <= _MAX_PORT_DIGITS and int(port) <= _MAX_PORT):
        return None, "Invalid port"

    netloc_host = f"[{hostname}]" if ":" in hostname else hostname
    return OutboundUrl(f"{scheme}://{userinfo}{netloc_host}{f':{int(port)}' if port else ''}{rest[end:]}", hostname), ""


def parse_outbound_hostname(url: str) -> tuple[str | None, str]:
    """Syntax check for an outbound URL. Returns (canonical hostname, "") or (None, error)."""
    target, error = parse_outbound_url(url)
    return (target.hostname, "") if target is not None else (None, error)
