"""Tests for routing/stream_config.py — StreamConfig defaults."""

from __future__ import annotations

from app.channels.routing.stream_config import StreamConfig


class TestStreamConfig:
    def test_defaults(self) -> None:
        config = StreamConfig()
        assert config.block_size == 500
        assert config.enable_code_fence_protection is True
        assert config.prefer_newline_breaks is True
        assert config.base_interval_seconds == 1.0
        assert config.min_interval_seconds == 0.3
        assert config.max_interval_seconds == 3.0
        assert config.progress_session_ttl_seconds == 3600.0
        assert config.coordinator_session_ttl_seconds == 3600.0
        assert config.min_first_send_size == 50
        assert config.max_retries == 3
        assert config.base_retry_delay_seconds == 0.5
        assert config.enable_compression is False
        assert config.compression_min_size == 500

    def test_frozen(self) -> None:
        config = StreamConfig()
        try:
            config.block_size = 1000  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass

    def test_custom_values(self) -> None:
        config = StreamConfig(block_size=1000, max_retries=5, enable_compression=True)
        assert config.block_size == 1000
        assert config.max_retries == 5
        assert config.enable_compression is True
