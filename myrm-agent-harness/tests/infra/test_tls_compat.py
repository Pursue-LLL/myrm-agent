"""Unit tests for infra/tls_compat.py: the context policy of the standard library and httpx.

The policy rewires the TLS context builders of the whole process, so every test starts from the libraries' own
builders and puts back whatever it found. What aiohttp, urllib3 and litellm hold is in ``test_tls_compat_libraries.py``.
"""

from __future__ import annotations

import inspect
import logging
import ssl
from pathlib import Path

import certifi
import httpx
import pytest
import urllib3.util.ssl_ as urllib3_ssl

from myrm_agent_harness.infra import tls_compat
from myrm_agent_harness.infra.tls_compat import (
    apply_global_tls_relaxation,
    create_httpx_client,
    tls_strict_disabled,
    with_node_system_ca,
)
from tests.support.mcp_testkit.tls_pki import generate_inspection_chain
from tests.support.tls_context_probe import STRICT_FLAG, der_of, is_truststore_context, loaded_cas
from tests.support.tls_loopback import CA_ENV_VARS, stand_in_system_trust

pytestmark = pytest.mark.usefixtures("pristine_tls")


class TestTlsStrictDisabled:
    """Tests for tls_strict_disabled() env var parsing."""

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE", "No", "OFF"])
    def test_disabled_values(self, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", value)
        assert tls_strict_disabled() is True

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "anything"])
    def test_enabled_values(self, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", value)
        assert tls_strict_disabled() is False

    def test_unset_defaults_to_strict(self) -> None:
        assert tls_strict_disabled() is False

    def test_whitespace_trimmed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "  0  ")
        assert tls_strict_disabled() is True


class TestWithNodeSystemCa:
    """A child process inherits none of the host's TLS policy, so a Node child is told to trust the system store."""

    @pytest.fixture
    def enterprise_network(self, pristine_tls: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")

    @pytest.mark.usefixtures("enterprise_network")
    def test_the_system_store_is_added_beside_the_callers_variables(self) -> None:
        env = {"PATH": "/usr/bin"}

        assert with_node_system_ca(env) == {"PATH": "/usr/bin", "NODE_USE_SYSTEM_CA": "1"}
        assert env == {"PATH": "/usr/bin"}

    @pytest.mark.usefixtures("enterprise_network")
    def test_no_environment_becomes_one_that_carries_it(self) -> None:
        assert with_node_system_ca(None) == {"NODE_USE_SYSTEM_CA": "1"}

    @pytest.mark.usefixtures("enterprise_network")
    def test_a_value_the_caller_sets_wins(self) -> None:
        assert with_node_system_ca({"NODE_USE_SYSTEM_CA": "0"}) == {"NODE_USE_SYSTEM_CA": "0"}

    @pytest.mark.usefixtures("enterprise_network")
    def test_a_differently_cased_declaration_is_the_callers_own_value_on_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tls_compat, "IS_WIN", True)

        assert with_node_system_ca({"node_use_system_ca": "0"}) == {"node_use_system_ca": "0"}

    @pytest.mark.usefixtures("enterprise_network")
    def test_a_differently_cased_name_is_another_variable_elsewhere(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tls_compat, "IS_WIN", False)

        assert with_node_system_ca({"node_use_system_ca": "0"}) == {
            "node_use_system_ca": "0",
            "NODE_USE_SYSTEM_CA": "1",
        }

    @pytest.mark.parametrize("value", [None, "1", "true", "anything"])
    def test_nothing_is_added_while_strict_verification_is_on(
        self, value: str | None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if value is not None:
            monkeypatch.setenv("MYRM_TLS_STRICT", value)
        env = {"PATH": "/usr/bin"}

        assert with_node_system_ca(env) is env
        assert with_node_system_ca(None) is None


class TestApplyGlobalTlsRelaxation:
    """Installing the policy: when it happens, and that it happens once."""

    def test_nothing_is_installed_while_strict(self) -> None:
        builder = ssl.create_default_context
        urllib3_builder = urllib3_ssl.create_urllib3_context

        assert apply_global_tls_relaxation() is False

        assert ssl.create_default_context is builder
        assert urllib3_ssl.create_urllib3_context is urllib3_builder

    def test_installs_when_strict_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        builder = ssl.create_default_context
        urllib3_builder = urllib3_ssl.create_urllib3_context

        assert apply_global_tls_relaxation() is True

        assert ssl.create_default_context is not builder
        assert inspect.unwrap(ssl.create_default_context) is builder
        assert urllib3_ssl.create_urllib3_context is not urllib3_builder
        assert inspect.unwrap(urllib3_ssl.create_urllib3_context) is urllib3_builder

    def test_a_second_call_does_not_wrap_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        builder = ssl.create_default_context
        urllib3_builder = urllib3_ssl.create_urllib3_context
        apply_global_tls_relaxation()
        installed = ssl.create_default_context
        urllib3_installed = urllib3_ssl.create_urllib3_context

        assert apply_global_tls_relaxation() is True

        assert ssl.create_default_context is installed
        assert inspect.unwrap(installed) is builder
        assert urllib3_ssl.create_urllib3_context is urllib3_installed
        assert inspect.unwrap(urllib3_installed) is urllib3_builder


class TestDefaultContextPolicy:
    """What a client-purpose default context becomes once the policy is installed."""

    @pytest.fixture(autouse=True)
    def _strict_off_and_installed(self, pristine_tls: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        apply_global_tls_relaxation()

    def test_default_trust_is_the_operating_system_store_with_verification_on(self) -> None:
        ctx = ssl.create_default_context()

        assert is_truststore_context(ctx)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert not ctx.verify_flags & STRICT_FLAG

    def test_the_bundled_ca_file_httpx_asks_for_means_the_default_trust(self) -> None:
        assert is_truststore_context(ssl.create_default_context(cafile=certifi.where()))

    @pytest.mark.usefixtures("inspectable_system_trust")
    @pytest.mark.parametrize("env_var", CA_ENV_VARS)
    def test_a_ca_bundle_the_environment_names_is_added(
        self, env_var: str, ca_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(env_var, str(ca_file))

        ctx = ssl.create_default_context()

        assert loaded_cas(ctx) == [der_of(ca_file)]
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    @pytest.mark.usefixtures("inspectable_system_trust")
    def test_an_unreadable_ca_bundle_is_skipped_with_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        garbage = tmp_path / "not-a-certificate.pem"
        garbage.write_text("this is not PEM")
        monkeypatch.setenv("NODE_EXTRA_CA_CERTS", str(garbage))

        with caplog.at_level(logging.WARNING, logger=tls_compat.logger.name):
            ctx = ssl.create_default_context()

        assert loaded_cas(ctx) == []
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert "tls_ca_bundle_skipped var=NODE_EXTRA_CA_CERTS" in caplog.text

    @pytest.mark.usefixtures("inspectable_system_trust")
    def test_a_missing_ca_bundle_is_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "absent.pem"))

        assert loaded_cas(ssl.create_default_context()) == []

    def test_a_pinned_ca_file_keeps_exactly_that_trust(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pinned_dir = tmp_path / "pinned"
        pinned_dir.mkdir()
        pinned = generate_inspection_chain(pinned_dir).ca_cert
        named_by_environment = generate_inspection_chain(tmp_path).ca_cert
        monkeypatch.setenv("NODE_EXTRA_CA_CERTS", str(named_by_environment))

        ctx = ssl.create_default_context(cafile=str(pinned))

        assert not is_truststore_context(ctx)
        assert loaded_cas(ctx) == [der_of(pinned)]
        assert not ctx.verify_flags & STRICT_FLAG

    def test_the_file_ssl_cert_file_names_joins_the_system_trust_wherever_it_is_passed_from(
        self, ca_file: Path, other_ca_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stand_in_system_trust(monkeypatch, ca_file)
        monkeypatch.setenv("SSL_CERT_FILE", str(other_ca_file))

        ctx = ssl.create_default_context(cafile=str(other_ca_file))

        assert set(loaded_cas(ctx)) == {der_of(ca_file), der_of(other_ca_file)}
        assert not ctx.verify_flags & STRICT_FLAG

    def test_another_pinned_file_stays_exactly_that_trust_while_ssl_cert_file_is_set(
        self, tmp_path: Path, ca_file: Path, other_ca_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pinned_dir = tmp_path / "pinned"
        pinned_dir.mkdir()
        pinned = generate_inspection_chain(pinned_dir).ca_cert
        stand_in_system_trust(monkeypatch, ca_file)
        monkeypatch.setenv("SSL_CERT_FILE", str(other_ca_file))

        ctx = ssl.create_default_context(cafile=str(pinned))

        assert loaded_cas(ctx) == [der_of(pinned)]

    def test_pinned_ca_data_keeps_exactly_that_trust(self, ca_file: Path) -> None:
        ctx = ssl.create_default_context(cadata=ca_file.read_text())

        assert not is_truststore_context(ctx)
        assert loaded_cas(ctx) == [der_of(ca_file)]
        assert not ctx.verify_flags & STRICT_FLAG

    def test_a_pinned_ca_directory_is_not_replaced_by_the_system_trust(self, tmp_path: Path) -> None:
        ctx = ssl.create_default_context(capath=str(tmp_path))

        assert not is_truststore_context(ctx)
        assert not ctx.verify_flags & STRICT_FLAG

    def test_server_purpose_contexts_are_untouched(self) -> None:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        assert not is_truststore_context(ctx)
        assert ctx.verify_flags & STRICT_FLAG

    def test_when_the_system_store_cannot_be_reached_the_standard_trust_is_kept(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def unreachable(*_args: object, **_kwargs: object) -> ssl.SSLContext:
            raise OSError("system trust store unavailable")

        monkeypatch.setattr("truststore.SSLContext", unreachable)

        with caplog.at_level(logging.WARNING, logger=tls_compat.logger.name):
            ctx = ssl.create_default_context()

        assert not is_truststore_context(ctx)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
        assert not ctx.verify_flags & STRICT_FLAG
        assert "tls_platform_trust_unavailable" in caplog.text

    def test_switching_the_toggle_off_stops_relaxing_new_contexts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_TLS_STRICT")

        ctx = ssl.create_default_context()

        assert not is_truststore_context(ctx)
        assert ctx.verify_flags & STRICT_FLAG

    def test_a_context_httpx_builds_after_the_install_trusts_the_system_store(self) -> None:
        assert is_truststore_context(httpx.create_ssl_context())


class TestCreateHttpxClient:
    """create_httpx_client() is the one construction point of the harness's httpx clients; it adds nothing to them."""

    async def test_builds_a_plain_async_client(self) -> None:
        async with create_httpx_client(timeout=5.0) as client:
            assert isinstance(client, httpx.AsyncClient)
            assert client.timeout.read == 5.0

    async def test_kwargs_reach_the_client(self) -> None:
        async with create_httpx_client(
            timeout=httpx.Timeout(30.0, connect=5.0),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        ) as client:
            assert client.timeout.connect == 5.0
            assert client.timeout.read == 30.0
            assert client.follow_redirects is False

    async def test_the_callers_verify_is_passed_through(self) -> None:
        async with create_httpx_client(verify=False) as client:
            assert isinstance(client, httpx.AsyncClient)
