"""Unit tests for Feishu stale message filtering."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.feishu.ws_transport import (
    _STALE_MSG_THRESHOLD_MS,
    FeishuWSTransport,
)


@pytest.fixture
def mock_sdk_data() -> MagicMock:
    """Create a mock SDK event data object."""
    data = MagicMock()
    data.header = MagicMock()
    data.event = MagicMock()
    return data


@pytest.fixture
def transport() -> FeishuWSTransport:
    """Create a FeishuWSTransport instance for testing."""
    return FeishuWSTransport(
        app_id="test_app_id",
        app_secret="test_secret",
    )


class TestStaleMessageFiltering:
    """Tests for stale message filtering logic."""

    def test_fresh_message_dispatched(
        self,
        transport: FeishuWSTransport,
        mock_sdk_data: MagicMock,
    ) -> None:
        """Fresh messages (< 20s old) should be dispatched."""
        loop = asyncio.new_event_loop()
        transport._running = True
        transport._loop = loop
        transport._on_event = AsyncMock()

        now_ms = int(time.time() * 1000)
        fresh_create_time = now_ms - 1000  # 1 second ago

        mock_sdk_data.header.create_time = str(fresh_create_time)

        transport._on_message_sync(mock_sdk_data)

        loop.close()

    def test_stale_message_dropped(
        self,
        transport: FeishuWSTransport,
        mock_sdk_data: MagicMock,
    ) -> None:
        """Stale messages (> 20s old) should be dropped."""
        loop = asyncio.new_event_loop()
        transport._running = True
        transport._loop = loop
        transport._on_event = AsyncMock()

        now_ms = int(time.time() * 1000)
        stale_create_time = now_ms - (_STALE_MSG_THRESHOLD_MS + 5000)  # 25s ago

        mock_sdk_data.header.create_time = str(stale_create_time)

        transport._on_message_sync(mock_sdk_data)

        loop.close()

    def test_threshold_boundary_dispatched(
        self,
        transport: FeishuWSTransport,
        mock_sdk_data: MagicMock,
    ) -> None:
        """Messages at exactly threshold boundary should be dispatched."""
        loop = asyncio.new_event_loop()
        transport._running = True
        transport._loop = loop
        transport._on_event = AsyncMock()

        now_ms = int(time.time() * 1000)
        boundary_create_time = now_ms - _STALE_MSG_THRESHOLD_MS  # Exactly 20s ago

        mock_sdk_data.header.create_time = str(boundary_create_time)

        transport._on_message_sync(mock_sdk_data)

        loop.close()

    def test_missing_create_time_dispatched(
        self,
        transport: FeishuWSTransport,
        mock_sdk_data: MagicMock,
    ) -> None:
        """Messages without create_time should be dispatched."""
        loop = asyncio.new_event_loop()
        transport._running = True
        transport._loop = loop
        transport._on_event = AsyncMock()

        mock_sdk_data.header.create_time = None

        transport._on_message_sync(mock_sdk_data)

        loop.close()

    def test_invalid_create_time_format_dispatched(
        self,
        transport: FeishuWSTransport,
        mock_sdk_data: MagicMock,
    ) -> None:
        """Messages with invalid create_time format should be dispatched."""
        loop = asyncio.new_event_loop()
        transport._running = True
        transport._loop = loop
        transport._on_event = AsyncMock()

        mock_sdk_data.header.create_time = "invalid"

        transport._on_message_sync(mock_sdk_data)

        loop.close()

    def test_missing_header_dispatched(
        self,
        transport: FeishuWSTransport,
        mock_sdk_data: MagicMock,
    ) -> None:
        """Messages without header should be dispatched."""
        loop = asyncio.new_event_loop()
        transport._running = True
        transport._loop = loop
        transport._on_event = AsyncMock()

        mock_sdk_data.header = None

        transport._on_message_sync(mock_sdk_data)

        loop.close()

    def test_not_running_no_dispatch(
        self,
        transport: FeishuWSTransport,
        mock_sdk_data: MagicMock,
    ) -> None:
        """Messages should not be dispatched if transport is not running."""
        transport._running = False
        transport._loop = asyncio.new_event_loop()
        transport._on_event = AsyncMock()

        now_ms = int(time.time() * 1000)
        mock_sdk_data.header.create_time = str(now_ms - 1000)

        transport._on_message_sync(mock_sdk_data)

        transport._loop.close()
