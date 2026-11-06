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
    "*.Straße.de",
    "example.com。",
    ".example.com．",
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
            ("ｅｖｉｌ.com", "evil.com"),
            ("evil。com", "evil.com"),
            ("evil.com。", "evil.com"),
            ("evil.com．", "evil.com"),
            ("evil.com｡", "evil.com"),
            ("[::1]:8080", "::1"),
            ("::1", "::1"),
            ("", ""),
            ("https://", ""),
        ],
    )
    def test_a_string_reduces_to_the_host_it_names(self, raw: str, host: str) -> None:
        assert canonical_host(raw) == host

    @pytest.mark.parametrize(
        ("raw", "host"),
        [
            ("münchen.de", "xn--mnchen-3ya.de"),
            ("日本語.jp", "xn--wgv71a119e.jp"),
            ("😀.com", "xn--e28h.com"),
            ("straße.de", "xn--strae-oqa.de"),
            ("Straße.DE", "xn--strae-oqa.de"),
            ("strasse.de", "strasse.de"),
            ("xn--strae-oqa.de", "xn--strae-oqa.de"),
            ("σας.gr", "xn--mxa8ab.gr"),
            ("ΣΑΣ.gr", "xn--mxa9ab.gr"),
            ("می\u200cخواهم.ir", "xn--mgbn2ecje63gr19l.ir"),
        ],
    )
    def test_a_non_ascii_label_is_the_punycode_a_browser_dials(self, raw: str, host: str) -> None:
        """Each value is the hostname the WHATWG URL parser gives for the same text; ``ß``, ``ς`` and the joiner stay."""
        assert canonical_host(raw) == host

    @pytest.mark.parametrize("name", ["a..b", "A" * 70 + ".com"])
    def test_an_ascii_name_is_read_as_written(self, name: str) -> None:
        assert canonical_host(name) == name.lower()

    @pytest.mark.parametrize("name", ["a\u0080b.é", "�.com"])
    def test_a_name_the_mapping_rejects_stays_as_written(self, name: str) -> None:
        assert canonical_host(name) == name

    def test_text_longer_than_a_dns_name_is_read_as_written(self) -> None:
        # Past 253 characters nothing can be dialed, so the mapping (its cost grows with the text) is skipped.
        too_long = ".".join(["é"] * 200) + ".com"

        assert canonical_host(too_long) == too_long
        assert canonical_host("é.com") == "xn--9ca.com"


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
            ("straße.de", "xn--strae-oqa.de"),
            ("*.Straße.de", "*.xn--strae-oqa.de"),
            ("example.com。", "example.com"),
            (".example.com．", "*.example.com"),
            ("*.example.com｡", "*.example.com"),
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

    @pytest.mark.parametrize("stop", ["。", "．", "｡"])
    def test_a_trailing_full_stop_of_any_kind_is_a_trailing_dot(self, stop: str) -> None:
        assert host_matches(f"example.com{stop}", ("example.com",))
        assert host_matches("example.com", (f"example.com{stop}",))
        assert host_matches(f"a.example.com{stop}", ("*.example.com",))
        assert not host_matches(f"example.com{stop}", ("example.org",))

    def test_sharp_s_is_not_ss(self) -> None:
        assert host_matches("straße.de", ("straße.de",))
        assert host_matches("straße.de", ("xn--strae-oqa.de",))
        assert host_matches("xn--strae-oqa.de", ("straße.de",))
        assert not host_matches("straße.de", ("strasse.de",))
        assert not host_matches("strasse.de", ("straße.de",))

    def test_final_sigma_and_a_joiner_name_hosts_of_their_own(self) -> None:
        assert host_matches("σας.gr", ("xn--mxa8ab.gr",))
        assert not host_matches("σας.gr", ("σασ.gr",))
        assert host_matches("می\u200cخواهم.ir", ("xn--mgbn2ecje63gr19l.ir",))
        assert not host_matches("می\u200cخواهم.ir", ("میخواهم.ir",))

    def test_a_numeric_ipv4_host_is_the_dotted_address_the_client_dials(self) -> None:
        assert host_matches("2130706433", ("127.0.0.1",))
        assert host_matches("0x7f.1", ("127.0.0.1",))
        assert host_matches("127.0.0.1", ("0177.0.0.1",))
        assert not host_matches("2130706434", ("127.0.0.1",))

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
