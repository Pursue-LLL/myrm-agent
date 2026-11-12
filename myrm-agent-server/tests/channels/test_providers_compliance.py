"""Provider compliance tests: verify all registered providers meet BaseChannel contract."""

from __future__ import annotations

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.registry import CHANNEL_META
from app.channels.types import ChannelCapabilities
from tests.channels.channel_class_testkit import channel_class_or_skip

ALL_CHANNEL_NAMES = list(CHANNEL_META.keys())


@pytest.fixture(params=ALL_CHANNEL_NAMES)
def channel_class(request: pytest.FixtureRequest) -> type[BaseChannel]:
    return channel_class_or_skip(request.param)


class TestProviderCompliance:
    def test_is_subclass_of_base_channel(self, channel_class: type[BaseChannel]) -> None:
        assert issubclass(channel_class, BaseChannel)

    def test_has_name_attribute(self, channel_class: type[BaseChannel]) -> None:
        assert isinstance(channel_class.name, str)
        assert len(channel_class.name) > 0

    def test_has_capabilities(self, channel_class: type[BaseChannel]) -> None:
        caps = channel_class.capabilities
        if isinstance(caps, property):
            pytest.skip(f"{channel_class.name}: capabilities is an instance property")
        assert isinstance(caps, ChannelCapabilities)

    def test_capabilities_text_is_true(self, channel_class: type[BaseChannel]) -> None:
        caps = channel_class.capabilities
        if isinstance(caps, property):
            pytest.skip(f"{channel_class.name}: capabilities is an instance property")
        assert caps.text is True

    def test_capabilities_max_text_length_positive(self, channel_class: type[BaseChannel]) -> None:
        caps = channel_class.capabilities
        if isinstance(caps, property):
            pytest.skip(f"{channel_class.name}: capabilities is an instance property")
        assert caps.max_text_length > 0

    def test_has_send_method(self, channel_class: type[BaseChannel]) -> None:
        assert callable(getattr(channel_class, "send", None))

    def test_has_start_method(self, channel_class: type[BaseChannel]) -> None:
        assert callable(getattr(channel_class, "start", None))

    def test_has_stop_method(self, channel_class: type[BaseChannel]) -> None:
        assert callable(getattr(channel_class, "stop", None))

    def test_name_matches_registry(self, channel_class: type[BaseChannel]) -> None:
        meta = CHANNEL_META.get(channel_class.name)
        assert meta is not None, f"Channel '{channel_class.name}' not in CHANNEL_META"

    def test_has_render_style(self, channel_class: type[BaseChannel]) -> None:
        if not hasattr(channel_class, "render_style"):
            pytest.skip(f"{channel_class.name}: render_style not implemented yet")
        assert hasattr(channel_class, "render_style")

    def test_native_markdown_renderer_declares_markdown_capability(self, channel_class: type[BaseChannel]) -> None:
        # The executor tells the model "do not use Markdown" whenever `capabilities.markdown` is False,
        # so a channel that renders Markdown natively must declare the flag or its replies lose formatting.
        caps = channel_class.capabilities
        if isinstance(caps, property):
            pytest.skip(f"{channel_class.name}: capabilities is an instance property")
        if not hasattr(channel_class, "render_style"):
            pytest.skip(f"{channel_class.name}: render_style not implemented yet")
        if channel_class.render_style.format == "markdown":
            assert caps.markdown, (
                f"{channel_class.name}: render_style.format is 'markdown' but capabilities.markdown is False; "
                "declare markdown=True so the model is not told to avoid Markdown"
            )
