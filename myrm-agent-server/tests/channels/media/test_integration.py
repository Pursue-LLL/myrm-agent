"""Integration tests with real HTTP requests.

Note: These tests require internet connectivity.
"""

import pytest

from app.channels.media import (
    MediaDownloadConfig,
    MediaDownloader,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_image_download():
    """Test downloading a real image from httpbin.org."""
    async with MediaDownloader() as downloader:
        result = await downloader.download("https://httpbin.org/image/png")

    assert result.success is True
    assert result.data is not None
    assert len(result.data) > 0
    assert result.content_type == "image/png"
    assert result.cached is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_size_limit():
    """Test size limit with real download."""
    config = MediaDownloadConfig(max_size_bytes=100)  # Very small limit

    async with MediaDownloader() as downloader:
        result = await downloader.download("https://httpbin.org/image/png", config=config)

    assert result.success is False  # Should exceed limit


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_cache_hit():
    """Test cache hit with real download."""
    async with MediaDownloader() as downloader:
        result1 = await downloader.download("https://httpbin.org/image/png")
        if not result1.success:
            pytest.skip("httpbin.org unreachable, skipping network-dependent test")

        assert result1.cached is False

        result2 = await downloader.download("https://httpbin.org/image/png")
        if not result2.success:
            pytest.skip("httpbin.org intermittent failure on second request")

        assert result2.cached is True
        assert result2.data == result1.data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_batch_download():
    """Test batch download with real URLs."""
    urls = [
        "https://httpbin.org/image/png",
        "https://httpbin.org/image/jpeg",
    ]

    async with MediaDownloader() as downloader:
        results = await downloader.download_many(urls)

    assert len(results) == 2
    assert all(r.success for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
