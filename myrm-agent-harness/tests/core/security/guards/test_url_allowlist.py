"""A skill's allowed-domains list and the host a request names are compared in one spelling.

The list is written by a person and the host is read from a URL, so ``münchen.de``, ``xn--mnchen-3ya.de`` and
``MÜNCHEN.de.`` must be one domain, while ``straße`` and ``strasse`` stay two: only the second is a different host
to the client that dials it.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.guards.url_allowlist import SSRFSecurityError, URLAllowlistGuard


def _allowed(allowed: list[str], host: str) -> bool:
    with URLAllowlistGuard.apply(allowed):
        try:
            URLAllowlistGuard.check(host)
        except SSRFSecurityError:
            return False
    return True


@pytest.mark.parametrize(
    ("entry", "host"),
    [
        ("münchen.de", "xn--mnchen-3ya.de"),
        ("xn--mnchen-3ya.de", "münchen.de"),
        ("münchen.de", "MÜNCHEN.de."),
        (".münchen.de", "api.xn--mnchen-3ya.de"),
        ("straße.de", "xn--strae-oqa.de"),
        ("example.com", "ｅｘａｍｐｌｅ.ｃｏｍ。"),
        ("127.0.0.1", "0x7f.1"),
        ("2130706433", "127.0.0.1"),
        ("  EXAMPLE.ORG  ", "sub.example.org"),
    ],
)
def test_an_entry_and_a_host_in_different_spellings_are_one_domain(entry: str, host: str) -> None:
    assert _allowed([entry], host)


@pytest.mark.parametrize(
    ("entry", "host"),
    [
        ("straße.de", "strasse.de"),
        ("strasse.de", "straße.de"),
        ("σας.gr", "ΣΑΣ.gr"),
        ("ΣΑΣ.gr", "σας.gr"),
        ("münchen.de", "evilxn--mnchen-3ya.de"),
        ("example.com", "notexample.com"),
        ("127.0.0.1", "2130706434"),
    ],
)
def test_different_hosts_stay_different_in_every_spelling(entry: str, host: str) -> None:
    assert not _allowed([entry], host)


def test_a_wildcard_entry_allows_every_host_and_an_empty_host_is_blocked() -> None:
    assert _allowed(["*"], "anything.example")
    assert not _allowed(["*"], "")


def test_no_list_restricts_nothing() -> None:
    with URLAllowlistGuard.apply(None):
        URLAllowlistGuard.check("anything.example")
