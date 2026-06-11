"""Tests for channel provider registry: lazy-loading, caching, thread-safety."""

from __future__ import annotations

import threading

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.registry import (
    CHANNEL_META,
    clear_cache,
    get_channel_class,
    get_channel_class_safe,
    load_enabled_channels,
    registered_names,
)


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    clear_cache()


class TestGetChannelClass:
    def test_loads_telegram(self) -> None:
        cls = get_channel_class("telegram")
        assert issubclass(cls, BaseChannel)
        assert cls.name == "telegram"

    def test_loads_webhook(self) -> None:
        cls = get_channel_class("webhook")
        assert issubclass(cls, BaseChannel)

    def test_caches_result(self) -> None:
        cls1 = get_channel_class("telegram")
        cls2 = get_channel_class("telegram")
        assert cls1 is cls2

    def test_raises_key_error_for_unknown(self) -> None:
        with pytest.raises(KeyError):
            get_channel_class("nonexistent_channel")


class TestGetChannelClassSafe:
    def test_returns_none_for_unknown(self) -> None:
        assert get_channel_class_safe("nonexistent_channel") is None

    def test_returns_class_for_known(self) -> None:
        cls = get_channel_class_safe("telegram")
        assert cls is not None
        assert issubclass(cls, BaseChannel)


class TestLoadEnabledChannels:
    def test_loads_enabled_only(self) -> None:
        configs = {
            "telegram": {"enabled": True},
            "webhook": {"enabled": False},
        }
        result = load_enabled_channels(configs)
        assert "telegram" in result
        assert "webhook" not in result

    def test_skips_unknown_channels(self) -> None:
        configs = {"nonexistent": {"enabled": True}}
        result = load_enabled_channels(configs)
        assert len(result) == 0

    def test_empty_config(self) -> None:
        result = load_enabled_channels({})
        assert len(result) == 0


class TestRegisteredNames:
    def test_returns_frozenset(self) -> None:
        names = registered_names()
        assert isinstance(names, frozenset)

    def test_contains_core_channels(self) -> None:
        names = registered_names()
        for expected in ("telegram", "discord", "slack", "feishu", "webhook"):
            assert expected in names

    def test_has_26_channels(self) -> None:
        assert len(registered_names()) == 26


class TestChannelMeta:
    def test_all_specs_have_display_name(self) -> None:
        for name, spec in CHANNEL_META.items():
            assert spec.display_name, f"{name} missing display_name"

    def test_all_specs_have_module_path(self) -> None:
        for name, spec in CHANNEL_META.items():
            assert spec.module.startswith("."), f"{name} module should be relative"


class TestThreadSafety:
    def test_concurrent_loads(self) -> None:
        results: list[type[BaseChannel]] = []
        errors: list[Exception] = []

        def load() -> None:
            try:
                cls = get_channel_class("telegram")
                results.append(cls)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=load) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)
