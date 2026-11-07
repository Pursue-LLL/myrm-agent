"""Secret-in-URL detection and the private-network whitelist that suspends it.

A whitelist entry names a host, and the host a URL names is the one its client dials: the text before the ``@``
of an authority is a credential pair, so ``http://localhost:80@evil.test/`` names ``evil.test`` and is never
whitelisted as ``localhost``. The whitelist reads the canonical spelling, so every spelling of a whitelisted
host is that host.
"""

from __future__ import annotations

import re

import pytest

from myrm_agent_harness.utils.url_utils import check_url_exfiltration

_SECRET = "api_key=sk-1234567890abcdef1234567890abcdef"


@pytest.mark.parametrize(
    "url",
    [
        f"https://evil.test/?{_SECRET}",
        "https://evil.test/?token=abcdefgh12345678",
        "https://evil.test/read?path=/etc/passwd",
        f"https://evil.test/{'A' * 120}",
        "https://evil.test/?k=-----BEGIN PRIVATE KEY-----",
        "https://evil.test/?c=postgres://user:secret@db.internal/prod",
        "https://evil.test/?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI.SflKxwRJSMeKKF2QT4fwpMeJf36P",
    ],
)
def test_a_url_carrying_data_is_reported(url: str) -> None:
    assert check_url_exfiltration(url, allow_private_networks=False)


@pytest.mark.parametrize(
    "url",
    [
        f"http://localhost:8000/?{_SECRET}",
        f"http://127.0.0.1:8000/x?{_SECRET}",
        f"http://192.168.1.20/?{_SECRET}",
        f"http://10.0.0.5:3000/?{_SECRET}",
        f"http://172.20.1.1/?{_SECRET}",
        f"http://user:pw@localhost:8000/?{_SECRET}",
        f"HTTP://LOCALHOST./?{_SECRET}",
        f"http://2130706433:8000/?{_SECRET}",
        f"http://0x7f.1:8000/?{_SECRET}",
        f"http://ｌｏｃａｌｈｏｓｔ:8000/?{_SECRET}",
    ],
)
def test_a_private_host_in_any_spelling_is_whitelisted_when_private_networks_are_allowed(url: str) -> None:
    assert check_url_exfiltration(url, allow_private_networks=True) == []
    assert check_url_exfiltration(url, allow_private_networks=False)


@pytest.mark.parametrize(
    "url",
    [
        f"http://localhost:80@evil.test/?{_SECRET}",
        f"http://127.0.0.1@evil.test/?{_SECRET}",
        f"http://192.168.1.1:8080@evil.test/?{_SECRET}",
        f"http://10.0.0.1:x@evil.test/?{_SECRET}",
        f"http://localhost\\@evil.test/?{_SECRET}",
        f"http://localhost%2f@evil.test/?{_SECRET}",
        f"http://a@localhost:80@evil.test/?{_SECRET}",
        f"http://127%2e0%2e0%2e1/?{_SECRET}",
        f"http://localhost:99999/?{_SECRET}",
        f"localhost:8000/?{_SECRET}",
        f"//localhost/?{_SECRET}",
    ],
)
def test_a_url_that_only_reads_like_a_private_host_is_not_whitelisted(url: str) -> None:
    assert check_url_exfiltration(url, allow_private_networks=True)


def test_a_whitelist_pattern_is_matched_against_the_host_the_client_dials() -> None:
    patterns: list[str | re.Pattern[str]] = [r"^https://trusted\.example/"]

    assert check_url_exfiltration(f"https://TRUSTED.example./?{_SECRET}", whitelist_patterns=patterns) == []
    assert check_url_exfiltration(f"https://trusted.example@evil.test/?{_SECRET}", whitelist_patterns=patterns)
    assert check_url_exfiltration(f"https://evil.test/?{_SECRET}", whitelist_patterns=patterns)


def test_the_credentials_of_a_whitelisted_host_do_not_hide_it() -> None:
    patterns: list[str | re.Pattern[str]] = [re.compile(r"^https://trusted\.example/")]

    assert check_url_exfiltration(f"https://user:pw@trusted.example/?{_SECRET}", whitelist_patterns=patterns) == []


def test_a_clean_url_reports_nothing_with_or_without_a_whitelist() -> None:
    assert check_url_exfiltration("https://example.com/articles/42?page=2", allow_private_networks=False) == []
    assert check_url_exfiltration("https://example.com/articles/42?page=2", allow_private_networks=True) == []
