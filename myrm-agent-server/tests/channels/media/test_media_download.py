"""Core tests for media download system."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.media import (
    ContentTypeError,
    LRUMemoryCache,
    MediaDownloadConfig,
    MediaDownloader,
    SizeExceededError,
    url_to_cache_key,
)


@pytest.mark.asyncio
async def test_config_validation():
    """Test MediaDownloadConfig validation."""
    # Valid config
    config = MediaDownloadConfig(max_size_bytes=1024)
    assert config.max_size_bytes == 1024

    # Invalid max_size_bytes
    with pytest.raises(ValueError, match="max_size_bytes must be > 0"):
        MediaDownloadConfig(max_size_bytes=-1)

    # Invalid timeout
    with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
        MediaDownloadConfig(timeout_seconds=-1)


@pytest.mark.asyncio
async def test_lru_cache():
    """Test LRU memory cache."""
    cache = LRUMemoryCache(max_size=3)

    # Set items
    await cache.set("key1", b"data1", "image/png")
    await cache.set("key2", b"data2", "image/jpeg")
    await cache.set("key3", b"data3", "image/gif")

    assert len(cache) == 3

    # Get item (moves to end)
    result = await cache.get("key1")
    assert result == (b"data1", "image/png")

    # Add 4th item (should evict key2, the LRU)
    await cache.set("key4", b"data4", "image/webp")

    assert len(cache) == 3
    assert await cache.get("key2") is None  # Evicted
    assert await cache.get("key1") is not None  # Still present (was accessed)

    # Clear cache
    await cache.clear()
    assert len(cache) == 0


@pytest.mark.asyncio
async def test_url_to_cache_key():
    """Test URL to cache key conversion."""
    url1 = "https://example.com/image.png"
    url2 = "https://example.com/image.jpg"

    key1 = url_to_cache_key(url1)
    key2 = url_to_cache_key(url2)

    assert len(key1) == 64  # SHA256 hex length
    assert key1 != key2

    # Same URL → same key
    assert url_to_cache_key(url1) == url_to_cache_key(url1)


@pytest.mark.asyncio
async def test_basic_download_success():
    """Test basic successful download."""
    # Create mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/png", "content-length": "4"}

    async def mock_aiter_bytes(chunk_size):
        yield b"test"

    mock_response.aiter_bytes = mock_aiter_bytes

    # Create mock HTTP client
    mock_client = MagicMock()

    # Mock stream() to return an async context manager
    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    mock_client.stream = MagicMock(return_value=MockStreamContext())

    with patch("app.channels.media.validators.async_validate_url_for_ssrf") as mock_ssrf:
        mock_ssrf.return_value = MagicMock(safe=True)

        downloader = MediaDownloader(http_client=mock_client, enable_default_cache=False)
        result = await downloader.download("https://example.com/test.png")

    assert result.success is True
    assert result.data == b"test"
    assert result.content_type == "image/png"
    assert result.size_bytes == 4
    assert result.cached is False


@pytest.mark.asyncio
async def test_size_limit_validation():
    """Test size limit validation during streaming."""
    # Mock streaming chunks that exceed limit
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/png"}

    async def mock_aiter_bytes(chunk_size):
        yield b"x" * 1000
        yield b"x" * 1000  # Total: 2000 bytes

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = MagicMock()

    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    mock_client.stream = MagicMock(return_value=MockStreamContext())

    config = MediaDownloadConfig(max_size_bytes=1500)  # Limit: 1500 bytes

    with patch("app.channels.media.validators.async_validate_url_for_ssrf") as mock_ssrf:
        mock_ssrf.return_value = MagicMock(safe=True)

        downloader = MediaDownloader(http_client=mock_client, enable_default_cache=False)
        result = await downloader.download("https://example.com/large.png", config=config)

    assert result.success is False
    assert isinstance(result.error, SizeExceededError)


@pytest.mark.asyncio
async def test_content_type_validation():
    """Test content-type validation."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/pdf"}

    async def mock_aiter_bytes(chunk_size):
        yield b"test"

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = MagicMock()

    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    mock_client.stream = MagicMock(return_value=MockStreamContext())

    # Only allow images
    config = MediaDownloadConfig(allowed_content_types=frozenset({"image/png", "image/jpeg"}))

    with patch("app.channels.media.validators.async_validate_url_for_ssrf") as mock_ssrf:
        mock_ssrf.return_value = MagicMock(safe=True)

        downloader = MediaDownloader(http_client=mock_client, enable_default_cache=False)
        result = await downloader.download("https://example.com/doc.pdf", config=config)

    assert result.success is False
    assert isinstance(result.error, ContentTypeError)


@pytest.mark.asyncio
async def test_cache_hit():
    """Test cache hit scenario."""
    cache = LRUMemoryCache()
    await cache.set(url_to_cache_key("https://example.com/cached.png"), b"cached_data", "image/png")

    mock_client = AsyncMock()

    downloader = MediaDownloader(http_client=mock_client, cache=cache)
    result = await downloader.download("https://example.com/cached.png")

    assert result.success is True
    assert result.data == b"cached_data"
    assert result.content_type == "image/png"
    assert result.cached is True

    # HTTP client should NOT be called
    mock_client.stream.assert_not_called()


@pytest.mark.asyncio
async def test_retry_on_timeout():
    """Test retry on timeout exception."""
    mock_client = AsyncMock()

    # First attempt: timeout, second attempt: success
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/png"}

    async def mock_aiter_bytes(chunk_size):
        yield b"test"

    mock_response.aiter_bytes = mock_aiter_bytes

    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    call_count = 0

    def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("Timeout")  # First attempt fails
        return MockStreamContext()  # Second succeeds

    mock_client.stream = mock_stream

    config = MediaDownloadConfig(enable_retry=True, max_retries=3)

    with patch("app.channels.media.validators.async_validate_url_for_ssrf") as mock_ssrf:
        mock_ssrf.return_value = MagicMock(safe=True)

        downloader = MediaDownloader(http_client=mock_client, enable_default_cache=False)
        result = await downloader.download("https://example.com/test.png", config=config)

    # Should succeed after retry
    assert result.success is True
    assert result.data == b"test"


@pytest.mark.asyncio
async def test_batch_download():
    """Test batch concurrent downloads."""
    urls = [
        "https://example.com/1.png",
        "https://example.com/2.png",
        "https://example.com/3.png",
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/png"}

    async def mock_aiter_bytes(chunk_size):
        yield b"test"

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_client = MagicMock()

    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    mock_client.stream = MagicMock(return_value=MockStreamContext())

    with patch("app.channels.media.validators.async_validate_url_for_ssrf") as mock_ssrf:
        mock_ssrf.return_value = MagicMock(safe=True)

        downloader = MediaDownloader(http_client=mock_client, enable_default_cache=False)
        results = await downloader.download_many(urls, max_concurrent=2)

    assert len(results) == 3
    assert all(r.success for r in results)
    assert all(r.data == b"test" for r in results)


@pytest.mark.asyncio
async def test_context_manager():
    """Test async context manager."""
    async with MediaDownloader() as downloader:
        assert downloader._http is not None

    # HTTP client should be closed after exiting context
    # (We can't easily test this without internal access)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
