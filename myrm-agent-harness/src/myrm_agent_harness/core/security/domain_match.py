"""One reading of the domain entries a person writes into a network allowlist or blocklist.

[INPUT]
- idna::uts46_remap (POS: UTS 46 name mapping, the normalization a browser applies to a host before it dials)

[OUTPUT]
- canonical_host(): the host a string names as a browser dials it, without scheme, path, port or trailing dot
- canonical_entry(): a list entry in canonical form, ``example.com`` or ``*.example.com``
- host_matches(): whether a host equals an entry or lies under a wildcard entry

[POS]
Shared by the permission engine (blocklist and per-domain approval), the browser domain filter and the taint
exemption, so that one entry means the same thing to every layer: ``example.com`` is exactly that host,
``*.example.com`` and ``.example.com`` are that host and everything under it, and the scheme, path and port a
person may paste along with an entry are ignored. A host is folded the way a browser folds it before it dials
(UTS 46: full-width letters and ideographic full stops become their plain forms, ``ß`` and ``ς`` stay themselves,
every non-ASCII label becomes Punycode), so a Unicode host, its Punycode spelling and its full-width spelling are one
host while ``straße`` and ``strasse`` are two. An entry that names no host (``*``, ``*.*``) stays in its list and
matches nothing, so a list made only of such entries still restricts instead of reading as unset. Text longer than a
DNS name is never a host: it is read as written, so a page cannot make a check slow or keep memory by naming itself
with a megabyte of characters.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

_WILDCARD_PREFIX = "*."
# A DNS name is at most 253 characters. Longer text skips the UTS 46 mapping, whose cost grows with the text, and stays
# out of the host cache, where distinct oversized strings would be kept alive.
_MAX_NAME_LENGTH = 253


def _host_text(raw: str) -> str:
    """Lowercase *raw* reduced to its host part; an IPv6 literal keeps its colons."""
    text = raw.strip().lower()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0]
    if text.startswith("["):
        return text[1 : text.index("]")] if "]" in text else text
    return text.split(":", 1)[0] if text.count(":") == 1 else text


def _fold(name: str) -> str:
    """*name* as a browser dials it: UTS 46 mapped, then every non-ASCII label as Punycode.

    ``ß``, ``ς`` and the joiners stay letters of their own, so ``straße.de`` and ``strasse.de`` are two hosts, as they
    are to the browser. A name that is ASCII, too long to be a host or rejected by the mapping stays as written.
    """
    if name.isascii() or len(name) > _MAX_NAME_LENGTH:
        return name
    import idna  # first needed by a non-ASCII name; the hosts of nearly every call are ASCII

    try:
        labels = idna.uts46_remap(name, std3_rules=False, transitional=False).split(".")
        return ".".join(
            label if label.isascii() else f"xn--{label.encode('punycode').decode('ascii')}" for label in labels
        )
    except UnicodeError:
        return name


def _read_host(raw: str) -> str:
    # The trailing dot is stripped after the fold, which is what turns an ideographic full stop into a dot.
    return _fold(_host_text(raw)).rstrip(".")


_read_short_host = lru_cache(maxsize=2048)(_read_host)


def canonical_host(raw: str) -> str:
    """The host *raw* names, as a browser dials it; empty when *raw* names none."""
    return _read_short_host(raw) if len(raw) <= _MAX_NAME_LENGTH else _read_host(raw)


@lru_cache(maxsize=1024)
def canonical_entry(raw: str) -> str:
    """*raw* as a list entry: ``example.com``, or ``*.example.com`` when it also covers the subdomains."""
    text = _fold(_host_text(raw))
    if text.startswith(_WILDCARD_PREFIX):
        return _WILDCARD_PREFIX + text[2:].rstrip(".")
    if text.startswith("."):
        return _WILDCARD_PREFIX + text[1:].rstrip(".")
    return text.rstrip(".")


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
