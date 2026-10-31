"""Unit tests for infra/tls_compat.py.

The policy rewires ``ssl.create_default_context`` for the whole process, so every test starts from the standard
library's own builder and puts back whatever it found.
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
    is_tls_hard_error,
    is_tls_transient_error,
    tls_strict_disabled,
)
from tests.support.mcp_testkit.tls_pki import generate_inspection_chain

_STRICT_FLAG = getattr(ssl, "VERIFY_X509_STRICT", 0)
_CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")

needs_strict_flag = pytest.mark.skipif(not _STRICT_FLAG, reason="VERIFY_X509_STRICT not available (Python < 3.13)")


@pytest.fixture(autouse=True)
def _pristine_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with the standard builders and no TLS environment, and restore both afterwards."""
    monkeypatch.setattr(ssl, "create_default_context", inspect.unwrap(ssl.create_default_context))
    monkeypatch.setattr(urllib3_ssl, "create_urllib3_context", inspect.unwrap(urllib3_ssl.create_urllib3_context))
    for name in ("MYRM_TLS_STRICT", *_CA_ENV_VARS):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def ca_file(tmp_path: Path) -> Path:
    return generate_inspection_chain(tmp_path).ca_cert


def _is_truststore_context(ctx: ssl.SSLContext) -> bool:
    return type(ctx).__module__.startswith("truststore")


def _loaded_cas(ctx: ssl.SSLContext) -> list[bytes]:
    """The CA certificates loaded into *ctx* itself, not the ones the operating system holds."""
    return ctx.get_ca_certs(binary_form=True)


@pytest.fixture
def inspectable_system_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand a plain context in for the system-store one, whose loaded CAs cannot be listed (``get_ca_certs`` raises)."""
    monkeypatch.setattr("truststore.SSLContext", ssl.SSLContext)


def _der(pem_file: Path) -> bytes:
    return ssl.PEM_cert_to_DER_cert(pem_file.read_text())


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


class TestApplyGlobalTlsRelaxation:
    """Installing the policy: when it happens, and that it happens once."""

    def test_nothing_is_installed_while_strict(self) -> None:
        builder = ssl.create_default_context
        urllib3_builder = urllib3_ssl.create_urllib3_context

        assert apply_global_tls_relaxation() is False

        assert ssl.create_default_context is builder
        assert urllib3_ssl.create_urllib3_context is urllib3_builder

    @needs_strict_flag
    def test_installs_when_strict_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        builder = ssl.create_default_context
        urllib3_builder = urllib3_ssl.create_urllib3_context

        assert apply_global_tls_relaxation() is True

        assert ssl.create_default_context is not builder
        assert inspect.unwrap(ssl.create_default_context) is builder
        assert urllib3_ssl.create_urllib3_context is not urllib3_builder
        assert inspect.unwrap(urllib3_ssl.create_urllib3_context) is urllib3_builder

    @needs_strict_flag
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


@needs_strict_flag
class TestDefaultContextPolicy:
    """What a client-purpose default context becomes once the policy is installed."""

    @pytest.fixture(autouse=True)
    def _strict_off_and_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        apply_global_tls_relaxation()

    def test_default_trust_is_the_operating_system_store_with_verification_on(self) -> None:
        ctx = ssl.create_default_context()

        assert _is_truststore_context(ctx)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert not ctx.verify_flags & _STRICT_FLAG

    def test_the_bundled_ca_file_httpx_asks_for_means_the_default_trust(self) -> None:
        assert _is_truststore_context(ssl.create_default_context(cafile=certifi.where()))

    @pytest.mark.usefixtures("inspectable_system_trust")
    @pytest.mark.parametrize("env_var", _CA_ENV_VARS)
    def test_a_ca_bundle_the_environment_names_is_added(
        self, env_var: str, ca_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(env_var, str(ca_file))

        ctx = ssl.create_default_context()

        assert _loaded_cas(ctx) == [_der(ca_file)]
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

        assert _loaded_cas(ctx) == []
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert "tls_ca_bundle_skipped var=NODE_EXTRA_CA_CERTS" in caplog.text

    @pytest.mark.usefixtures("inspectable_system_trust")
    def test_a_missing_ca_bundle_is_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "absent.pem"))

        assert _loaded_cas(ssl.create_default_context()) == []

    def test_a_pinned_ca_file_keeps_exactly_that_trust(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pinned_dir = tmp_path / "pinned"
        pinned_dir.mkdir()
        pinned = generate_inspection_chain(pinned_dir).ca_cert
        named_by_environment = generate_inspection_chain(tmp_path).ca_cert
        monkeypatch.setenv("NODE_EXTRA_CA_CERTS", str(named_by_environment))

        ctx = ssl.create_default_context(cafile=str(pinned))

        assert not _is_truststore_context(ctx)
        assert _loaded_cas(ctx) == [_der(pinned)]
        assert not ctx.verify_flags & _STRICT_FLAG

    def test_pinned_ca_data_keeps_exactly_that_trust(self, ca_file: Path) -> None:
        ctx = ssl.create_default_context(cadata=ca_file.read_text())

        assert not _is_truststore_context(ctx)
        assert _loaded_cas(ctx) == [_der(ca_file)]
        assert not ctx.verify_flags & _STRICT_FLAG

    def test_server_purpose_contexts_are_untouched(self) -> None:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        assert not _is_truststore_context(ctx)
        assert ctx.verify_flags & _STRICT_FLAG

    def test_when_the_system_store_cannot_be_reached_the_standard_trust_is_kept(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def unreachable(*_args: object, **_kwargs: object) -> ssl.SSLContext:
            raise OSError("system trust store unavailable")

        monkeypatch.setattr("truststore.SSLContext", unreachable)

        with caplog.at_level(logging.WARNING, logger=tls_compat.logger.name):
            ctx = ssl.create_default_context()

        assert not _is_truststore_context(ctx)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
        assert not ctx.verify_flags & _STRICT_FLAG
        assert "tls_platform_trust_unavailable" in caplog.text

    def test_switching_the_toggle_off_stops_relaxing_new_contexts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_TLS_STRICT")

        ctx = ssl.create_default_context()

        assert not _is_truststore_context(ctx)
        assert ctx.verify_flags & _STRICT_FLAG

    def test_a_context_httpx_builds_after_the_install_trusts_the_system_store(self) -> None:
        assert _is_truststore_context(httpx.create_ssl_context())


@needs_strict_flag
class TestUrllib3Relaxation:
    def test_urllib3_contexts_lose_only_the_strict_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        apply_global_tls_relaxation()

        ctx = urllib3_ssl.create_urllib3_context()

        assert not ctx.verify_flags & _STRICT_FLAG
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_urllib3_contexts_stay_strict_after_the_toggle_goes_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        apply_global_tls_relaxation()
        monkeypatch.delenv("MYRM_TLS_STRICT")

        assert urllib3_ssl.create_urllib3_context().verify_flags & _STRICT_FLAG


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


class TestIsTlsHardVsTransient:
    """Hard certificate rejections fail fast; interrupted handshakes retry."""

    @pytest.mark.parametrize(
        "msg",
        [
            # Real verified Python tracebacks (local socket reproduction).
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate",
            "unable to get local issuer certificate",
            "unable to verify the first certificate",
            "hostname mismatch, certificate is not valid for 'api.example.com'",
            "certificate has expired",
            "ERR_TLS_CERT_ALTNAME_INVALID",
            "BasicConstraints of CA cert not marked critical",
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
            "self-signed certificate in certificate chain",
            # The same wordings with another separator or apostrophe, and the codes Node and OpenSSL print alone.
            "Error: DEPTH_ZERO_SELF_SIGNED_CERT",
            "SELF_SIGNED_CERT_IN_CHAIN",
            "Hostname doesn\u2019t match certificate",
            "basic_constraints of CA cert",
            "[SSL: CERTIFICATE_VERIFY_FAILED]",
            "cert has expired",
        ],
    )
    def test_hard_errors_fail_fast(self, msg: str) -> None:
        assert is_tls_hard_error(msg) is True
        assert is_tls_transient_error(msg) is False

    @pytest.mark.parametrize(
        "msg",
        [
            # Bun mislabel: reset mid-handshake, no certificate ever rejected.
            "unknown certificate verification error",
            "UNKNOWN_CERTIFICATE_VERIFICATION_ERROR",
            # Real verified Python tracebacks (local socket reproduction).
            "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol",
            "[Errno 32] Broken pipe",
            "ssl.SSLError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] handshake failure",
        ],
    )
    def test_transient_errors_retryable(self, msg: str) -> None:
        assert is_tls_transient_error(msg) is True
        assert is_tls_hard_error(msg) is False

    @pytest.mark.parametrize(
        "msg",
        [
            "Connection refused",
            "DNS resolution failed",
            "Timeout exceeded",
            "Rate limit exceeded",
            "Invalid API key",
        ],
    )
    def test_ignores_non_tls_errors(self, msg: str) -> None:
        assert is_tls_transient_error(msg) is False
        assert is_tls_hard_error(msg) is False
