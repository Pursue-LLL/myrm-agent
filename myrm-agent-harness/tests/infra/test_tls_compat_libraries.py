"""Unit tests for the library wiring of infra/tls_compat.py: aiohttp, urllib3, urllib and litellm.

Each library keeps its own reference to a context builder or a ready-made context; these tests pin that every one of
them ends up on the policy, and that the library internals the policy reaches into are still where it expects them.
"""

from __future__ import annotations

import inspect
import logging
import ssl
import sys
import types
from pathlib import Path

import aiohttp.connector
import pytest
import urllib3.connection
import urllib3.util
import urllib3.util.ssl_ as urllib3_ssl

from myrm_agent_harness.infra import tls_compat
from myrm_agent_harness.infra.tls_compat import apply_global_tls_relaxation
from tests.support.tls_context_probe import STRICT_FLAG, der_of, is_truststore_context, loaded_cas, needs_strict_flag
from tests.support.tls_loopback import CA_ENV_VARS

pytestmark = pytest.mark.usefixtures("pristine_tls")


@needs_strict_flag
class TestInstalledBindings:
    """Every place a library holds its own reference to a context builder ends up on the policy."""

    @pytest.fixture(autouse=True)
    def _strict_off(self, pristine_tls: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")

    def test_the_https_default_of_urllib_and_http_client_is_the_policy_builder(self) -> None:
        builder = ssl.create_default_context

        apply_global_tls_relaxation()

        assert ssl._create_default_https_context is ssl.create_default_context
        assert inspect.unwrap(ssl._create_default_https_context) is builder

    def test_a_https_default_the_host_replaced_is_left_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ssl, "_create_default_https_context", ssl._create_unverified_context)

        apply_global_tls_relaxation()

        assert ssl._create_default_https_context is ssl._create_unverified_context

    @pytest.mark.parametrize("module", [urllib3_ssl, urllib3.connection, urllib3.util], ids=lambda m: m.__name__)
    def test_every_urllib3_module_holding_the_builder_is_rebound(self, module: types.ModuleType) -> None:
        builder = module.create_urllib3_context

        apply_global_tls_relaxation()

        assert module.create_urllib3_context is urllib3_ssl.create_urllib3_context
        assert inspect.unwrap(module.create_urllib3_context) is builder

    def test_a_module_outside_urllib3_is_not_rebound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        builder = urllib3_ssl.create_urllib3_context
        elsewhere = types.ModuleType("not_urllib3")
        elsewhere.create_urllib3_context = builder  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "not_urllib3", elsewhere)

        apply_global_tls_relaxation()

        assert elsewhere.create_urllib3_context is builder

    def test_the_aiohttp_default_context_is_rebuilt_through_the_policy(self) -> None:
        before = aiohttp.connector._SSL_CONTEXT_VERIFIED
        unverified = aiohttp.connector._SSL_CONTEXT_UNVERIFIED

        apply_global_tls_relaxation()

        rebuilt = aiohttp.connector._SSL_CONTEXT_VERIFIED
        assert rebuilt is not before
        assert is_truststore_context(rebuilt)
        assert rebuilt.verify_mode == ssl.CERT_REQUIRED
        assert not rebuilt.verify_flags & STRICT_FLAG
        assert aiohttp.connector._SSL_CONTEXT_UNVERIFIED is unverified

    def test_aiohttp_is_not_imported_just_to_be_rebuilt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delitem(sys.modules, "aiohttp.connector")

        apply_global_tls_relaxation()

        assert "aiohttp.connector" not in sys.modules

    def test_an_aiohttp_without_the_builder_is_reported_not_fatal(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delattr(aiohttp.connector, "_make_ssl_context")
        before = aiohttp.connector._SSL_CONTEXT_VERIFIED

        with caplog.at_level(logging.WARNING, logger=tls_compat.logger.name):
            assert apply_global_tls_relaxation() is True

        assert aiohttp.connector._SSL_CONTEXT_VERIFIED is before
        assert "tls_aiohttp_default_context_unavailable" in caplog.text


class TestLibraryContracts:
    """The library internals the policy reaches into; when a release moves one of them these fail first."""

    def test_aiohttp_keeps_its_verified_default_context_and_the_builder_behind_it(self) -> None:
        assert isinstance(aiohttp.connector._SSL_CONTEXT_VERIFIED, ssl.SSLContext)
        assert callable(aiohttp.connector._make_ssl_context)

    def test_urllib3_builds_its_contexts_from_a_module_level_class_in_its_ssl_module(self) -> None:
        assert urllib3_ssl.SSLContext is ssl.SSLContext
        assert callable(urllib3_ssl.create_urllib3_context)
        assert urllib3.connection.create_urllib3_context is urllib3_ssl.create_urllib3_context  # type: ignore[attr-defined]

    def test_the_standard_library_keeps_a_replaceable_https_default(self) -> None:
        assert ssl._create_default_https_context is ssl.create_default_context

    def test_litellm_keeps_its_contexts_in_a_clearable_cache(self) -> None:
        from litellm.llms.custom_httpx import http_handler

        assert isinstance(http_handler._ssl_context_cache, dict)


@needs_strict_flag
class TestUrllib3Policy:
    """What a context urllib3 (``requests``) builds becomes once the policy is installed."""

    @pytest.fixture(autouse=True)
    def _strict_off_and_installed(self, pristine_tls: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_TLS_STRICT", "0")
        apply_global_tls_relaxation()

    def test_default_trust_is_the_operating_system_store_with_verification_on(self) -> None:
        ctx = urllib3_ssl.create_urllib3_context()

        assert is_truststore_context(ctx)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert not ctx.verify_flags & STRICT_FLAG

    @pytest.mark.usefixtures("inspectable_system_trust")
    @pytest.mark.parametrize("env_var", CA_ENV_VARS)
    def test_a_ca_bundle_the_environment_names_is_added(
        self, env_var: str, ca_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(env_var, str(ca_file))

        assert loaded_cas(urllib3_ssl.create_urllib3_context()) == [der_of(ca_file)]

    def test_a_minimum_version_the_caller_asks_for_still_applies(self) -> None:
        ctx = urllib3_ssl.create_urllib3_context(ssl_minimum_version=ssl.TLSVersion.TLSv1_3)

        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_when_the_system_store_cannot_be_reached_the_standard_trust_is_kept(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def unreachable(*_args: object, **_kwargs: object) -> ssl.SSLContext:
            raise OSError("system trust store unavailable")

        monkeypatch.setattr("truststore.SSLContext", unreachable)

        with caplog.at_level(logging.WARNING, logger=tls_compat.logger.name):
            ctx = urllib3_ssl.create_urllib3_context()

        assert not is_truststore_context(ctx)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert not ctx.verify_flags & STRICT_FLAG
        assert "tls_platform_trust_unavailable" in caplog.text

    def test_switching_the_toggle_off_stops_relaxing_new_contexts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_TLS_STRICT")

        ctx = urllib3_ssl.create_urllib3_context()

        assert not is_truststore_context(ctx)
        assert ctx.verify_flags & STRICT_FLAG

    def test_installing_twice_changes_nothing(self) -> None:
        context_class = urllib3_ssl.SSLContext
        builder = urllib3_ssl.create_urllib3_context

        apply_global_tls_relaxation()

        assert urllib3_ssl.SSLContext is context_class
        assert urllib3_ssl.create_urllib3_context is builder
        assert inspect.unwrap(builder) is not builder
