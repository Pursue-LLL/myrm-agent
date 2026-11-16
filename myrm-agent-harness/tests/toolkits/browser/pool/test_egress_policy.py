"""What the egress guard admits: the SSRF policy applied to one connection, and when a guard applies at all.

The guard resolves a destination once and dials only what this policy returned, so every verdict below is the verdict
on the address that gets connected.
"""

from __future__ import annotations

import socket
from collections.abc import Sequence

import pytest

from myrm_agent_harness.toolkits.browser.pool import EgressGuard, create_egress_guard
from myrm_agent_harness.toolkits.browser.pool.egress_guard import _warn_environment_proxy
from myrm_agent_harness.toolkits.browser.pool.egress_policy import (
    EgressRefusedError,
    environment_proxy_configured,
    resolve_public_addresses,
)
from tests.toolkits.browser._fake_dns import process_dns

_PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy")


@pytest.fixture(autouse=True)
def _no_environment_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """A runner behind a proxy must not decide what these tests see."""
    for name in _PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)


def _answers(monkeypatch: pytest.MonkeyPatch, *addresses: str) -> None:
    """Make every name resolve to all of ``addresses``, in that order."""

    def getaddrinfo(host: str, port: int, *_args: object, **_kwargs: object) -> Sequence[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


class TestResolvePublicAddresses:
    @pytest.mark.parametrize("address", ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
    def test_a_public_literal_is_its_own_answer(self, address: str) -> None:
        assert resolve_public_addresses(address, 443) == (address,)

    @pytest.mark.parametrize(
        "host",
        [
            "127.0.0.1",
            "10.1.2.3",
            "172.16.0.9",
            "192.168.1.1",
            "169.254.169.254",
            "0.0.0.0",  # noqa: S104 - a destination to refuse, not an address to bind
            "::1",
            "fe80::1",
            "fd00::5",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
        ],
    )
    def test_an_internal_literal_is_refused_without_a_lookup(self, host: str, monkeypatch: pytest.MonkeyPatch) -> None:
        def no_lookup(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("a literal address needs no lookup")

        monkeypatch.setattr(socket, "getaddrinfo", no_lookup)

        with pytest.raises(EgressRefusedError):
            resolve_public_addresses(host, 80)

    @pytest.mark.parametrize("host", ["localhost", "metadata.google.internal"])
    def test_an_internal_name_is_refused_whatever_it_resolves_to(
        self, host: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _answers(monkeypatch, "93.184.216.34")  # an answer that looks public does not rescue it

        with pytest.raises(EgressRefusedError):
            resolve_public_addresses(host, 80)

    @pytest.mark.parametrize("spelling", ["2130706433", "0x7f.1", "017700000001", "127.1"])
    def test_a_legacy_spelling_of_loopback_is_refused_by_what_the_resolver_makes_of_it(self, spelling: str) -> None:
        with pytest.raises(EgressRefusedError):
            resolve_public_addresses(spelling, 80)  # the real resolver: numeric spellings need no network

    def test_a_single_label_name_is_judged_by_its_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _answers(monkeypatch, "172.18.0.5")  # a container network name

        with pytest.raises(EgressRefusedError, match="non-public"):
            resolve_public_addresses("postgres", 5432)

    def test_a_name_that_resolves_to_public_addresses_returns_them_once_each(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _answers(monkeypatch, "93.184.216.34", "93.184.216.35", "93.184.216.34")

        assert resolve_public_addresses("example.org", 443) == ("93.184.216.34", "93.184.216.35")

    @pytest.mark.parametrize(
        "answers",
        [
            ("127.0.0.1",),
            ("169.254.169.254",),
            ("93.184.216.34", "10.0.0.7"),  # one internal answer taints the name: the browser may pick it
            ("10.0.0.7", "93.184.216.34"),
        ],
    )
    def test_a_name_with_any_internal_answer_is_refused(
        self, answers: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _answers(monkeypatch, *answers)

        with pytest.raises(EgressRefusedError, match="non-public"):
            resolve_public_addresses("rebind.example.org", 443)

    def test_the_dns_answer_of_a_nip_style_name_is_what_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _answers(monkeypatch, "169.254.169.254")

        with pytest.raises(EgressRefusedError):
            resolve_public_addresses("169.254.169.254.nip.io", 80)

    def test_an_unresolvable_name_is_a_plain_lookup_failure(self) -> None:
        with process_dns({}, unresolvable={"gone.example.org"}), pytest.raises(socket.gaierror):
            resolve_public_addresses("gone.example.org", 80)

    def test_a_host_the_operator_listed_keeps_its_internal_answers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_ALLOWED_INTERNAL_HOSTS", "wiki.corp.example")
        _answers(monkeypatch, "10.20.30.40")

        assert resolve_public_addresses("wiki.corp.example", 443) == ("10.20.30.40",)

    def test_a_listed_host_does_not_exempt_another_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_ALLOWED_INTERNAL_HOSTS", "wiki.corp.example")
        _answers(monkeypatch, "10.20.30.40")

        with pytest.raises(EgressRefusedError):
            resolve_public_addresses("other.corp.example", 443)


class TestEnvironmentProxy:
    def test_no_variable_means_no_proxy(self) -> None:
        assert environment_proxy_configured() is False

    @pytest.mark.parametrize("name", [*_PROXY_VARIABLES, *(name.upper() for name in _PROXY_VARIABLES)])
    def test_any_of_the_proxy_variables_counts(self, name: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(name, "http://proxy.corp.example:3128")

        assert environment_proxy_configured() is True

    def test_an_empty_variable_is_no_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "")

        assert environment_proxy_configured() is False


class TestCreateEgressGuard:
    def test_the_shield_on_and_no_environment_proxy_gives_a_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_ENABLE_SSRF_SHIELD", raising=False)

        assert isinstance(create_egress_guard(), EgressGuard)

    def test_a_disabled_shield_leaves_nothing_to_enforce(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_ENABLE_SSRF_SHIELD", "false")

        assert create_egress_guard() is None

    def test_an_environment_proxy_owns_the_egress_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_ENABLE_SSRF_SHIELD", raising=False)
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp.example:3128")

        assert create_egress_guard() is None

    def test_the_proxy_notice_is_logged_once_per_process(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("MYRM_ENABLE_SSRF_SHIELD", raising=False)
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp.example:3128")
        _warn_environment_proxy.cache_clear()

        with caplog.at_level("WARNING"):
            for _ in range(3):
                create_egress_guard()

        assert [record.getMessage() for record in caplog.records].count(
            "Browser egress guard not used: the environment routes HTTP traffic through a proxy, "
            "so the proxy's operator must enforce the egress policy"
        ) == 1
