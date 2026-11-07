"""One reading of the domain entries a person writes into a network allowlist or blocklist.

[INPUT]
- utils.url_syntax::canonical_hostname (POS: the one ASCII spelling of a host, the one the outbound URL gates dial)

[OUTPUT]
- canonical_name(): the canonical host a host text names; text that names no host stands for itself, lowercased
- canonical_host(): the host a string names, without scheme, path, port or trailing dot
- canonical_entry(): a list entry in canonical form, ``example.com`` or ``*.example.com``
- host_matches(): whether a host equals an entry or lies under a wildcard entry

[POS]
Shared by the permission engine (blocklist and per-domain approval), the browser domain filter and the taint
exemption, so that one entry means the same thing to every layer: ``example.com`` is exactly that host,
``*.example.com`` and ``.example.com`` are that host and everything under it, and the scheme, path and port a
person may paste along with an entry are ignored. Entries and hosts are folded by the same function the outbound
URL gates dial with, so a Unicode host, its Punycode spelling and its full-width spelling are one host while
``straße`` and ``strasse`` are two. An entry that names no host (``*``, ``*.*``) stays in its list and matches
nothing, so a list made only of such entries still restricts instead of reading as unset.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from myrm_agent_harness.utils.url_syntax import canonical_hostname

_WILDCARD_PREFIX = "*."


def _host_text(raw: str) -> str:
    """*raw* reduced to its host part; an IPv6 literal keeps its colons."""
    text = raw.strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0]
    if text.startswith("["):
        return text[1 : text.index("]")] if "]" in text else text
    return text.split(":", 1)[0] if text.count(":") == 1 else text


def canonical_name(text: str) -> str:
    """The canonical host *text* names; text that names no host stands for itself and matches nothing."""
    return canonical_hostname(text) or text.lower().rstrip(".")


def canonical_host(raw: str) -> str:
    """The host *raw* names, as the outbound URL gates dial it; empty when *raw* names none."""
    return canonical_name(_host_text(raw))


@lru_cache(maxsize=1024)
def canonical_entry(raw: str) -> str:
    """*raw* as a list entry: ``example.com``, or ``*.example.com`` when it also covers the subdomains."""
    text = _host_text(raw)
    if text.startswith(_WILDCARD_PREFIX):
        return _WILDCARD_PREFIX + canonical_name(text[2:])
    if text.startswith("."):
        return _WILDCARD_PREFIX + canonical_name(text[1:])
    return canonical_name(text)


def host_matches(host: str, entries: Iterable[str]) -> bool:
    """Whether *host* equals one of *entries* or lies under one of its wildcard entries."""
    name = canonical_host(host)
    if not name:
        return False
    for entry in entries:
        pattern = canonical_entry(entry)
        if pattern.startswith(_WILDCARD_PREFIX):
            apex = pattern[2:]
            if apex and "*" not in apex and (name == apex or name.endswith(f".{apex}")):
                return True
        elif "*" not in pattern and pattern == name:
            return True
    return False
