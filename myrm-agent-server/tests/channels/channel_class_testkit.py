"""Channel-class lookup for tests that visit every registered channel.

A channel whose optional SDK is not installed (``ChannelSpec.sdk_package``) cannot be imported, so a test that
visits all channels leaves it out instead of failing. Any other import failure is a defect and propagates.
"""

from __future__ import annotations

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.registry import CHANNEL_META, get_channel_class, get_channel_spec


def _missing_sdk(name: str) -> str | None:
    """The optional SDK package ``name`` needs and lacks; ``None`` when its class imports."""
    try:
        get_channel_class(name)
    except ImportError:
        spec = get_channel_spec(name)
        if spec is None or not spec.sdk_package:
            raise
        return spec.sdk_package
    return None


def channel_class_or_skip(name: str) -> type[BaseChannel]:
    """The class registered under ``name``; skips the running test when the channel's optional SDK is not installed."""
    sdk = _missing_sdk(name)
    if sdk is not None:
        pytest.skip(f"{name}: optional SDK {sdk} is not installed")
    return get_channel_class(name)


def channels_missing_their_sdk() -> frozenset[str]:
    """The registered channels whose optional SDK is not installed."""
    return frozenset(name for name in CHANNEL_META if _missing_sdk(name) is not None)
