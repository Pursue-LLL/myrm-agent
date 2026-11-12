"""Unit tests for the options ContextFactory builds.

Validates that Accept-Language headers are correctly derived from locale
settings, that module-level constants are never mutated (shallow copy safety),
that a context refuses downloads unless its owner asks for them, and that a
context in the user's own browser (through the extension) asks for no override.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser import enhancers
from myrm_agent_harness.toolkits.browser.pool import ContextType, EmulationConfig, RoundRobinProxyPool
from myrm_agent_harness.toolkits.browser.pool.context_factory import (
    _DEFAULT_CONTEXT_OPTIONS,
    ContextFactory,
    _sync_accept_language,
)


class TestDownloadDefault:
    """The browser's own default saves every download a page starts and holds it until the context closes."""

    @pytest.mark.parametrize("context_type", [context_type.value for context_type in ContextType])
    def test_a_context_refuses_downloads_by_default(self, context_type: str) -> None:
        options = ContextFactory()._build_context_options(context_type, None, None)

        assert options["accept_downloads"] is False

    def test_the_owner_of_a_context_can_ask_for_downloads(self) -> None:
        options = ContextFactory()._build_context_options(ContextType.AGENT.value, None, {"accept_downloads": True})

        assert options["accept_downloads"] is True


class TestExtensionAttachedContext:
    """The extension's debugger refuses some overrides and the rest would change the user's own tab."""

    @staticmethod
    def _factory_that_would_override_everything() -> ContextFactory:
        return ContextFactory(
            proxy_pool=RoundRobinProxyPool.from_urls(["http://127.0.0.1:8080"]),
            default_emulation=EmulationConfig(
                locale="ja-JP", timezone="Asia/Tokyo", viewport=(390, 844), user_agent="Mozilla/5.0 (iPhone)"
            ),
        )

    @pytest.mark.parametrize("context_type", [context_type.value for context_type in ContextType])
    def test_it_asks_for_no_override_of_the_users_browser(self, context_type: str) -> None:
        options = self._factory_that_would_override_everything()._build_context_options(
            context_type, None, None, "key", extension_attached=True
        )

        assert options == {"no_viewport": True, "accept_downloads": False}

    def test_a_context_of_a_launched_browser_keeps_its_viewport_proxy_and_emulation(self) -> None:
        options = self._factory_that_would_override_everything()._build_context_options(
            ContextType.AGENT.value, None, None, "key"
        )

        assert {"viewport", "proxy", "locale", "timezone_id", "user_agent"} <= options.keys()

    def test_the_owner_of_the_context_can_still_ask_for_downloads(self) -> None:
        options = ContextFactory()._build_context_options(
            ContextType.AGENT.value, None, {"accept_downloads": True}, extension_attached=True
        )

        assert options == {"no_viewport": True, "accept_downloads": True}

    @pytest.mark.parametrize(("extension_attached", "stealth_injected"), [(True, False), (False, True)])
    async def test_stealth_scripts_are_never_injected_into_the_users_browser(
        self, monkeypatch: pytest.MonkeyPatch, extension_attached: bool, stealth_injected: bool
    ) -> None:
        apply_stealth = AsyncMock()
        monkeypatch.setattr(ContextFactory, "_apply_stealth", staticmethod(apply_stealth))
        monkeypatch.setattr(enhancers, "install_document_script_injection", AsyncMock())
        context = MagicMock()
        context.add_init_script = AsyncMock()
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)

        await ContextFactory().create_context(browser, ContextType.STEALTH.value, extension_attached=extension_attached)

        assert apply_stealth.await_count == int(stealth_injected)


class TestSyncAcceptLanguage:
    """Tests for _sync_accept_language header alignment."""

    def test_region_locale_produces_two_values(self) -> None:
        ctx: dict[str, object] = {"extra_http_headers": {"Accept-Language": "old"}}
        _sync_accept_language(ctx, "ja-JP")
        headers = ctx["extra_http_headers"]
        assert isinstance(headers, dict)
        assert headers["Accept-Language"] == "ja-JP,ja;q=0.9"

    def test_bare_language_locale(self) -> None:
        ctx: dict[str, object] = {"extra_http_headers": {"Accept-Language": "old"}}
        _sync_accept_language(ctx, "en")
        headers = ctx["extra_http_headers"]
        assert isinstance(headers, dict)
        assert headers["Accept-Language"] == "en;q=1"

    def test_no_headers_key_is_noop(self) -> None:
        ctx: dict[str, object] = {"viewport": {"width": 1920}}
        _sync_accept_language(ctx, "ja-JP")
        assert "extra_http_headers" not in ctx

    def test_headers_not_dict_is_noop(self) -> None:
        ctx: dict[str, object] = {"extra_http_headers": "invalid"}
        _sync_accept_language(ctx, "ja-JP")
        assert ctx["extra_http_headers"] == "invalid"

    def test_does_not_mutate_module_constant(self) -> None:
        original_lang = None
        orig_headers = _DEFAULT_CONTEXT_OPTIONS.get("extra_http_headers")
        if isinstance(orig_headers, dict):
            original_lang = orig_headers.get("Accept-Language")

        ctx = dict(_DEFAULT_CONTEXT_OPTIONS)
        _sync_accept_language(ctx, "fr-FR")

        current_headers = _DEFAULT_CONTEXT_OPTIONS.get("extra_http_headers")
        assert isinstance(current_headers, dict)
        assert current_headers.get("Accept-Language") == original_lang

    def test_other_headers_preserved(self) -> None:
        ctx: dict[str, object] = {
            "extra_http_headers": {
                "Accept": "text/html",
                "Accept-Language": "old",
                "DNT": "1",
            }
        }
        _sync_accept_language(ctx, "de-DE")
        headers = ctx["extra_http_headers"]
        assert isinstance(headers, dict)
        assert headers["Accept"] == "text/html"
        assert headers["DNT"] == "1"
        assert headers["Accept-Language"] == "de-DE,de;q=0.9"

    @pytest.mark.parametrize(
        ("locale", "expected"),
        [
            ("zh-CN", "zh-CN,zh;q=0.9"),
            ("en-US", "en-US,en;q=0.9"),
            ("ko-KR", "ko-KR,ko;q=0.9"),
            ("pt-BR", "pt-BR,pt;q=0.9"),
        ],
    )
    def test_common_locales(self, locale: str, expected: str) -> None:
        ctx: dict[str, object] = {"extra_http_headers": {"Accept-Language": "old"}}
        _sync_accept_language(ctx, locale)
        headers = ctx["extra_http_headers"]
        assert isinstance(headers, dict)
        assert headers["Accept-Language"] == expected
