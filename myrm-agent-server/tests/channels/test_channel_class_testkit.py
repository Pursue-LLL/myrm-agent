"""A test that visits every channel leaves out the channels whose optional SDK is missing, and only those."""

from __future__ import annotations

import pytest

from app.channels.core.base import BaseChannel
from tests.channels import channel_class_testkit as testkit


def _imports_fail(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Make the lookup of the given channels fail the way an uninstalled package does."""
    lookup = testkit.get_channel_class

    def failing(name: str) -> type[BaseChannel]:
        if name in names:
            raise ModuleNotFoundError(f"No module named {name!r}")
        return lookup(name)

    monkeypatch.setattr(testkit, "get_channel_class", failing)


def test_an_importable_channel_resolves() -> None:
    assert testkit.channel_class_or_skip("telegram").name == "telegram"


def test_a_channel_whose_optional_sdk_is_missing_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _imports_fail(monkeypatch, "discord")

    with pytest.raises(pytest.skip.Exception, match="discord.py"):
        testkit.channel_class_or_skip("discord")


def test_the_channels_missing_their_sdk_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    _imports_fail(monkeypatch, "discord", "feishu")

    assert testkit.channels_missing_their_sdk() == {"discord", "feishu"}


def test_a_channel_without_an_optional_sdk_that_fails_to_import_is_a_defect(monkeypatch: pytest.MonkeyPatch) -> None:
    _imports_fail(monkeypatch, "telegram")

    with pytest.raises(ModuleNotFoundError):
        testkit.channel_class_or_skip("telegram")
    with pytest.raises(ModuleNotFoundError):
        testkit.channels_missing_their_sdk()
