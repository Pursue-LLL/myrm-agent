"""One reading of a domain list entry: what ``example.com``, ``*.example.com`` and ``.example.com`` cover.

The permission engine, the browser domain filter and the taint exemption all match hosts through ``host_matches``,
so an entry a person writes once means the same thing to every layer.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.domain_match import canonical_entry, canonical_host, host_matches

_ENTRIES = [
    "example.com",
    "EXAMPLE.com",
    "*.example.com",
    ".example.com",
    ".Example.COM:8443",
    "https://*.example.com/x",
    "example.com.",
    "*.münchen.de",
    "*",
    "*.",
    ".",
    "",
]


class TestCanonicalHost:
    @pytest.mark.parametrize(
        ("raw", "host"),
        [
            ("Example.COM", "example.com"),
            ("example.com.", "example.com"),
            ("example.com:8443", "example.com"),
            ("https://Example.com:8443/path?q=1", "example.com"),
            ("münchen.de", "xn--mnchen-3ya.de"),
            ("ｅｖｉｌ.com", "evil.com"),
            ("evil。com", "evil.com"),
            ("[::1]:8080", "::1"),
            ("::1", "::1"),
            ("", ""),
            ("https://", ""),
        ],
    )
    def test_a_string_reduces_to_the_host_it_names(self, raw: str, host: str) -> None:
        assert canonical_host(raw) == host

    def test_a_name_the_idna_codec_rejects_stays_as_written(self) -> None:
        assert canonical_host("a..b") == "a..b"
        assert canonical_host("A" * 70 + ".com") == "a" * 70 + ".com"


class TestCanonicalEntry:
    @pytest.mark.parametrize(
        ("raw", "entry"),
        [
            ("example.com", "example.com"),
            ("EXAMPLE.com", "example.com"),
            ("example.com:8443", "example.com"),
            ("https://example.com/x", "example.com"),
            ("example.com.", "example.com"),
            ("*.example.com", "*.example.com"),
            (".example.com", "*.example.com"),
            (".Example.COM:8443", "*.example.com"),
            ("https://*.example.com/x", "*.example.com"),
            ("*.münchen.de", "*.xn--mnchen-3ya.de"),
            ("*", "*"),
            ("*.", "*."),
            (".", "*."),
            ("", ""),
        ],
    )
    def test_every_spelling_of_an_entry_shares_one_canonical_form(self, raw: str, entry: str) -> None:
        assert canonical_entry(raw) == entry

    @pytest.mark.parametrize("raw", _ENTRIES)
    def test_the_canonical_form_reads_as_itself(self, raw: str) -> None:
        entry = canonical_entry(raw)

        assert canonical_entry(entry) == entry


class TestHostMatches:
    @pytest.mark.parametrize("entry", ["example.com", "EXAMPLE.com", "example.com:8443", "https://example.com/x"])
    def test_a_plain_entry_names_exactly_that_host(self, entry: str) -> None:
        assert host_matches("example.com", (entry,))
        assert host_matches("Example.COM.", (entry,))
        for other in ("a.example.com", "notexample.com", "example.com.evil.com", "example.org", ""):
            assert not host_matches(other, (entry,))

    @pytest.mark.parametrize("entry", ["*.example.com", ".example.com", ".Example.COM:8443", "https://*.example.com/x"])
    def test_a_wildcard_entry_names_the_host_and_everything_under_it(self, entry: str) -> None:
        for host in ("example.com", "a.example.com", "a.b.example.com", "A.Example.COM."):
            assert host_matches(host, (entry,))
        for other in ("notexample.com", "example.com.evil.com", "example.org", "com", ""):
            assert not host_matches(other, (entry,))

    def test_an_idn_entry_and_its_punycode_host_meet(self) -> None:
        assert host_matches("xn--mnchen-3ya.de", ("münchen.de",))
        assert host_matches("münchen.de", ("*.xn--mnchen-3ya.de",))
        assert host_matches("a.münchen.de", ("*.münchen.de",))

    def test_a_fullwidth_host_is_the_ascii_host_the_client_dials(self) -> None:
        assert host_matches("ｅｖｉｌ.com", ("evil.com",))
        assert host_matches("evil。com", ("*.evil.com",))

    def test_an_ipv6_literal_matches_by_address(self) -> None:
        assert host_matches("::1", ("[::1]",))
        assert host_matches("[::1]:3000", ("::1",))
        assert not host_matches("::2", ("::1",))

    @pytest.mark.parametrize("entry", ["*", "*.*", "*.", ".", "", " ", "a.*.com", "*example.com", "https://"])
    def test_an_entry_naming_no_host_matches_nothing(self, entry: str) -> None:
        for host in ("example.com", "a.example.com", "localhost", "", "*"):
            assert not host_matches(host, (entry,))

    def test_any_entry_of_the_list_may_match(self) -> None:
        entries = ("a.com", "*.b.org", "localhost")

        assert host_matches("x.b.org", entries)
        assert host_matches("localhost", entries)
        assert not host_matches("c.net", entries)

    def test_an_empty_list_matches_nothing(self) -> None:
        assert not host_matches("example.com", ())
