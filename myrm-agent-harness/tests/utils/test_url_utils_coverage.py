"""Tests for url_utils - covering URL dedup keys, display URLs, extraction, validation, and SSRF protection."""

from __future__ import annotations

import socket
from typing import NoReturn
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from myrm_agent_harness.core.security.guards.ssrf import (
    SSRFResult,
    async_validate_url_for_ssrf,
    validate_url_for_ssrf,
)
from myrm_agent_harness.utils.url_utils import (
    build_host_resolver_rules,
    create_dns_pin_map,
    extract_domain,
    is_blocked_ip,
    is_file_url,
    is_image_url,
    is_valid_image_url,
    readable_url,
    url_dedup_key,
    validate_scheme_and_hostname,
)

_AddrInfo = tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]


class TestUrlDedupKey:
    def test_basic_key(self) -> None:
        assert url_dedup_key("https://Example.COM/Path/") == "https://example.com/path"

    def test_removes_www(self) -> None:
        assert "www." not in url_dedup_key("https://www.example.com/page")

    def test_ignores_fragment(self) -> None:
        assert "#" not in url_dedup_key("https://example.com/page#section")

    def test_fragment_is_kept_on_request_decoded_and_with_its_case(self) -> None:
        assert (
            url_dedup_key("https://www.Example.com/P/#%E5%8E%86Sec", keep_fragment=True)
            == "https://example.com/p#历Sec"
        )

    def test_kept_fragments_tell_anchors_apart(self) -> None:
        one = url_dedup_key("https://example.com/p#a", keep_fragment=True)
        other = url_dedup_key("https://example.com/p#b", keep_fragment=True)
        assert one != other
        assert url_dedup_key("https://example.com/p", keep_fragment=True) != one

    def test_decodes_percent_encoding(self) -> None:
        assert "中文" in url_dedup_key("https://example.com/%E4%B8%AD%E6%96%87")

    def test_preserves_query(self) -> None:
        assert "key=value" in url_dedup_key("https://example.com/page?key=value")

    def test_root_path_not_stripped(self) -> None:
        assert url_dedup_key("https://example.com/") == "https://example.com/"

    def test_spelling_variants_share_one_key(self) -> None:
        assert url_dedup_key("https://www.Example.com/A%20b/#top") == url_dedup_key("https://example.com/a b")

    @pytest.mark.parametrize("url", ["", "http://[::1"])
    def test_unusable_url_is_returned_unchanged(self, url: str) -> None:
        assert url_dedup_key(url) == url


class TestReadableUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bilibili.com/video/BV1hp4y1k7SV",
            "https://Example.COM/Path/?Key=Value#Section",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://example.com/a%20b%2Fc?x=1%26y%3D2#frag%23ment",
        ],
    )
    def test_the_providers_url_is_kept_as_it_is(self, url: str) -> None:
        assert readable_url(url) == url

    def test_non_ascii_escapes_become_characters(self) -> None:
        url = "https://zh.wikipedia.org/wiki/%E8%8B%B1%E9%9B%84%E8%81%94%E7%9B%9F#%E5%8E%86%E5%8F%B2"
        assert readable_url(url) == "https://zh.wikipedia.org/wiki/英雄联盟#历史"

    def test_lowercase_hex_digits_are_decoded(self) -> None:
        assert readable_url("https://example.com/%e4%b8%ad") == "https://example.com/中"

    def test_ascii_escapes_between_non_ascii_ones_stay_escaped(self) -> None:
        assert readable_url("https://example.com/%E4%B8%AD%20%E6%96%87") == "https://example.com/中%20文"

    def test_a_redirect_wrapper_keeps_its_query_structure(self) -> None:
        wrapper = "https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1%26y%3D2&sa=U"
        assert parse_qs(urlparse(readable_url(wrapper)).query)["q"] == ["https://example.com/a?x=1&y=2"]

    @pytest.mark.parametrize(
        "escaped",
        [
            "%E4%B8",  # truncated sequence
            "%FF%FE",  # not UTF-8
            "%E4%B8%AD%FF",  # one bad byte keeps the whole run escaped
            "%E2%80%8B",  # zero-width space
            "%C2%A0",  # no-break space
            "%E3%80%80",  # ideographic space
            "%E2%80%AE",  # right-to-left override
        ],
    )
    def test_escapes_that_are_not_readable_characters_stay_escaped(self, escaped: str) -> None:
        url = f"https://example.com/{escaped}"
        assert readable_url(url) == url

    @pytest.mark.parametrize("url", ["", "http://[::1"])
    def test_unusable_url_is_returned_unchanged(self, url: str) -> None:
        assert readable_url(url) == url


class TestExtractDomain:
    def test_basic(self) -> None:
        assert extract_domain("https://example.com/page") == "example.com"

    def test_removes_www(self) -> None:
        assert extract_domain("https://www.example.com") == "example.com"

    def test_invalid_url(self) -> None:
        assert extract_domain("") == ""


class TestIsValidImageUrl:
    def test_https_valid(self) -> None:
        assert is_valid_image_url("https://cdn.example.com/img.png") is True

    def test_http_invalid(self) -> None:
        assert is_valid_image_url("http://cdn.example.com/img.png") is False

    def test_localhost_invalid(self) -> None:
        assert is_valid_image_url("https://localhost/img.png") is False

    def test_private_ip_invalid(self) -> None:
        assert is_valid_image_url("https://192.168.1.1/img.png") is False
        assert is_valid_image_url("https://10.0.0.1/img.png") is False
        assert is_valid_image_url("https://172.16.0.1/img.png") is False


class TestIsImageUrl:
    def test_jpg(self) -> None:
        assert is_image_url("https://example.com/photo.jpg") is True

    def test_png_with_query(self) -> None:
        assert is_image_url("https://example.com/photo.png?w=100") is True

    def test_not_image(self) -> None:
        assert is_image_url("https://example.com/page.html") is False

    def test_svg(self) -> None:
        assert is_image_url("https://example.com/icon.svg") is True


class TestIsFileUrl:
    def test_file_with_extension(self) -> None:
        assert is_file_url("https://example.com/doc.pdf") is True

    def test_no_extension(self) -> None:
        assert is_file_url("https://example.com/page") is False


class TestSSRFResult:
    def test_safe_result_fields(self) -> None:
        result = SSRFResult(safe=True, hostname="example.com")
        assert result.safe is True
        assert result.error == ""
        assert result.hostname == "example.com"

    def test_unsafe_result(self) -> None:
        result = SSRFResult(safe=False, error="blocked")
        assert result.safe is False
        assert result.error == "blocked"


class TestCheckIpBlocked:
    def test_loopback_blocked(self) -> None:
        assert is_blocked_ip("127.0.0.1") is True

    def test_private_blocked(self) -> None:
        assert is_blocked_ip("192.168.1.1") is True
        assert is_blocked_ip("10.0.0.1") is True

    def test_public_allowed(self) -> None:
        assert is_blocked_ip("8.8.8.8") is False

    def test_link_local_blocked(self) -> None:
        assert is_blocked_ip("169.254.169.254") is True


class TestValidateSchemeAndHostname:
    def test_valid_https(self) -> None:
        hostname, error = validate_scheme_and_hostname("https://example.com/page")
        assert hostname == "example.com"
        assert error == ""

    def test_blocked_scheme(self) -> None:
        hostname, error = validate_scheme_and_hostname("ftp://example.com")
        assert hostname is None
        assert "scheme" in error.lower()

    def test_missing_hostname(self) -> None:
        hostname, error = validate_scheme_and_hostname("https://")
        assert hostname is None
        assert "hostname" in error.lower()

    def test_blocked_hostname(self) -> None:
        hostname, error = validate_scheme_and_hostname("https://localhost/path")
        assert hostname is None
        assert "blocked" in error.lower()

    def test_cloud_metadata_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://169.254.169.254/latest/meta-data/")
        assert hostname is None
        assert "blocked" in error.lower()

    def test_parser_confusing_tab_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://evil.com\t@169.254.169.254/")
        assert hostname is None
        assert "parser-confusing" in error.lower()

    def test_parser_confusing_newline_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://evil.com\n@169.254.169.254/")
        assert hostname is None
        assert "parser-confusing" in error.lower()

    def test_parser_confusing_backslash_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://evil.com\\@169.254.169.254/")
        assert hostname is None
        assert "parser-confusing" in error.lower()

    def test_parser_confusing_carriage_return_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://evil.com\r@169.254.169.254/")
        assert hostname is None
        assert "parser-confusing" in error.lower()

    def test_trailing_dot_normalized(self) -> None:
        hostname, error = validate_scheme_and_hostname("https://example.com./page")
        assert hostname == "example.com"
        assert error == ""

    def test_trailing_dot_localhost_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("https://localhost./admin")
        assert hostname is None
        assert "blocked" in error.lower()

    def test_local_suffix_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://printer.local/")
        assert hostname is None
        assert "suffix" in error.lower()

    def test_cluster_local_suffix_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://api.cluster.local/")
        assert hostname is None
        assert "suffix" in error.lower()

    def test_svc_suffix_blocked(self) -> None:
        hostname, error = validate_scheme_and_hostname("http://my-svc.svc/")
        assert hostname is None
        assert "suffix" in error.lower()

    def test_normal_url_not_affected(self) -> None:
        hostname, error = validate_scheme_and_hostname("https://example.com/page")
        assert hostname == "example.com"
        assert error == ""


class TestValidateUrlForSsrf:
    def test_safe_public_url(self) -> None:
        result = validate_url_for_ssrf("https://example.com")
        assert result.safe is True
        assert len(result.resolved_ips) > 0

    def test_blocked_localhost(self) -> None:
        result = validate_url_for_ssrf("https://localhost")
        assert result.safe is False

    def test_blocked_scheme(self) -> None:
        result = validate_url_for_ssrf("ftp://example.com")
        assert result.safe is False

    def test_ip_literal_blocked(self) -> None:
        result = validate_url_for_ssrf("https://127.0.0.1/path")
        assert result.safe is False

    def test_ip_literal_public(self) -> None:
        result = validate_url_for_ssrf("https://8.8.8.8")
        assert result.safe is True
        assert result.resolved_ips == ("8.8.8.8",)

    def test_dns_failure(self) -> None:
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("DNS failed")):
            result = validate_url_for_ssrf("https://nonexistent.invalid")
            assert result.safe is False
            assert "DNS" in result.error

    def test_dns_resolves_to_private(self) -> None:
        mock_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]
        with patch("socket.getaddrinfo", return_value=mock_result):
            result = validate_url_for_ssrf("https://evil.example.com")
            assert result.safe is False
            assert "Blocked resolved IP" in result.error


class TestAsyncValidateUrlForSsrf:
    @pytest.mark.asyncio
    async def test_safe_public_url(self) -> None:
        result = await async_validate_url_for_ssrf("https://example.com")
        assert result.safe is True

    @pytest.mark.asyncio
    async def test_blocked_scheme(self) -> None:
        result = await async_validate_url_for_ssrf("ftp://example.com")
        assert result.safe is False

    @pytest.mark.asyncio
    async def test_ip_literal_blocked(self) -> None:
        result = await async_validate_url_for_ssrf("https://127.0.0.1")
        assert result.safe is False

    @pytest.mark.asyncio
    async def test_ip_literal_public(self) -> None:
        result = await async_validate_url_for_ssrf("https://8.8.8.8")
        assert result.safe is True

    @pytest.mark.asyncio
    async def test_dns_failure(self) -> None:
        async def mock_getaddrinfo(*args: object, **kwargs: object) -> NoReturn:
            raise socket.gaierror("DNS failed")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo
            result = await async_validate_url_for_ssrf("https://nonexistent.invalid")
            assert result.safe is False

    @pytest.mark.asyncio
    async def test_dns_resolves_to_private(self) -> None:
        mock_result: list[_AddrInfo] = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 0))]

        async def mock_getaddrinfo(*args: object, **kwargs: object) -> list[_AddrInfo]:
            return mock_result

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo
            result = await async_validate_url_for_ssrf("https://evil.example.com")
            assert result.safe is False


class TestDnsPinningHelpers:
    def test_create_dns_pin_map_success(self) -> None:
        results = [
            SSRFResult(safe=True, hostname="a.com", resolved_ips=("1.2.3.4",)),
            SSRFResult(safe=True, hostname="b.com", resolved_ips=("5.6.7.8",)),
        ]
        pin_map, error = create_dns_pin_map(results)
        assert error is None
        assert pin_map == {"a.com": "1.2.3.4", "b.com": "5.6.7.8"}

    def test_create_dns_pin_map_with_unsafe(self) -> None:
        results = [
            SSRFResult(safe=True, hostname="a.com", resolved_ips=("1.2.3.4",)),
            SSRFResult(safe=False, error="blocked", hostname="evil.com"),
        ]
        pin_map, error = create_dns_pin_map(results)
        assert pin_map == {}
        assert error == "blocked"

    def test_build_host_resolver_rules(self) -> None:
        results = [
            SSRFResult(safe=True, hostname="a.com", resolved_ips=("1.2.3.4",)),
            SSRFResult(safe=True, hostname="b.com", resolved_ips=("5.6.7.8",)),
        ]
        rules = build_host_resolver_rules(results)
        assert "MAP a.com 1.2.3.4" in rules
        assert "MAP b.com 5.6.7.8" in rules

    def test_build_host_resolver_rules_skips_unsafe(self) -> None:
        results = [
            SSRFResult(safe=False, error="blocked", hostname="evil.com"),
        ]
        rules = build_host_resolver_rules(results)
        assert rules == ""

    def test_build_host_resolver_rules_empty(self) -> None:
        assert build_host_resolver_rules([]) == ""
