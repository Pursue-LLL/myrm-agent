"""Unit tests for Slack user resolver and mention annotation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.user_resolver import UserResolverCache
from app.channels.providers.slack.user_resolver import SlackUserResolver


@pytest.fixture
def mock_slack_client():
    """Mock SlackClient for testing."""
    client = MagicMock()
    client.users_info = AsyncMock()
    return client


@pytest.fixture
def resolver(mock_slack_client):
    """SlackUserResolver with mocked API client."""
    return SlackUserResolver(mock_slack_client, cache_ttl=60, cache_max_size=100)


class TestUserResolverCache:
    """Test UserResolverCache LRU+TTL cache."""

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test cache miss returns sentinel object."""
        cache = UserResolverCache(ttl_seconds=60, max_size=100)
        result = await cache.get("U123")
        assert isinstance(result, object)
        assert result is not None
        assert not isinstance(result, str)

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit returns cached value."""
        cache = UserResolverCache(ttl_seconds=60, max_size=100)
        await cache.set("U123", "Alice")
        result = await cache.get("U123")
        assert result == "Alice"

    @pytest.mark.asyncio
    async def test_cache_negative_result(self):
        """Test negative result caching (None value)."""
        cache = UserResolverCache(ttl_seconds=60, max_size=100)
        await cache.set("U123", None)
        result = await cache.get("U123")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self):
        """Test cache entry expires after TTL."""
        cache = UserResolverCache(ttl_seconds=0.1, max_size=100)
        await cache.set("U123", "Alice")

        # Immediate hit
        result = await cache.get("U123")
        assert result == "Alice"

        # Wait for expiration
        await asyncio.sleep(0.15)
        result = await cache.get("U123")
        assert isinstance(result, object)  # Miss (expired)
        assert not isinstance(result, str)

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        """Test LRU eviction when max_size reached."""
        cache = UserResolverCache(ttl_seconds=60, max_size=3)

        await cache.set("U1", "Alice")
        await asyncio.sleep(0.01)  # Ensure different timestamps
        await cache.set("U2", "Bob")
        await asyncio.sleep(0.01)
        await cache.set("U3", "Charlie")

        # Cache full (3/3)
        assert (await cache.get("U1")) == "Alice"
        assert (await cache.get("U2")) == "Bob"
        assert (await cache.get("U3")) == "Charlie"

        # Add 4th entry, should evict U1 (oldest)
        await cache.set("U4", "David")

        assert isinstance(await cache.get("U1"), object)  # Evicted
        assert (await cache.get("U2")) == "Bob"
        assert (await cache.get("U3")) == "Charlie"
        assert (await cache.get("U4")) == "David"

    @pytest.mark.asyncio
    async def test_cache_stats(self):
        """Test cache statistics."""
        cache = UserResolverCache(ttl_seconds=60, max_size=100)
        await cache.set("U1", "Alice")
        await cache.set("U2", "Bob")

        stats = cache.get_stats()
        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 60

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """Test cache clear."""
        cache = UserResolverCache(ttl_seconds=60, max_size=100)
        await cache.set("U1", "Alice")
        await cache.set("U2", "Bob")

        await cache.clear()

        assert isinstance(await cache.get("U1"), object)  # Miss
        assert isinstance(await cache.get("U2"), object)  # Miss
        assert cache.get_stats()["size"] == 0

    @pytest.mark.asyncio
    async def test_cache_eviction_callback_invoked(self):
        """Test eviction callback is invoked when LRU eviction occurs."""
        callback = MagicMock()
        cache = UserResolverCache(ttl_seconds=60, max_size=2, eviction_callback=callback)

        # Fill cache (2 entries)
        await cache.set("U1", "Alice")
        await cache.set("U2", "Bob")
        callback.assert_not_called()

        # Add 3rd entry, should trigger eviction and callback
        await cache.set("U3", "Charlie")
        callback.assert_called_once()

        # Add 4th entry, another eviction
        callback.reset_mock()
        await cache.set("U4", "David")
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_eviction_callback_exception_handled(self):
        """Test eviction callback exception does not break cache operation."""
        # Callback that raises exception
        callback = MagicMock(side_effect=RuntimeError("Callback error"))
        cache = UserResolverCache(ttl_seconds=60, max_size=2, eviction_callback=callback)

        # Fill cache
        await cache.set("U1", "Alice")
        await cache.set("U2", "Bob")

        # Add 3rd entry, callback raises exception but cache still works
        await cache.set("U3", "Charlie")
        callback.assert_called_once()

        # Verify cache still functional (U1 evicted, U2/U3 remain)
        assert isinstance(await cache.get("U1"), object)  # Evicted
        assert (await cache.get("U2")) == "Bob"
        assert (await cache.get("U3")) == "Charlie"

    @pytest.mark.asyncio
    async def test_cache_no_callback_for_update(self):
        """Test eviction callback not invoked when updating existing key."""
        callback = MagicMock()
        cache = UserResolverCache(ttl_seconds=60, max_size=2, eviction_callback=callback)

        # Fill cache
        await cache.set("U1", "Alice")
        await cache.set("U2", "Bob")

        # Update existing key (no eviction)
        await cache.set("U1", "Alice Updated")
        callback.assert_not_called()


class TestSlackUserResolver:
    """Test SlackUserResolver."""

    @pytest.mark.asyncio
    async def test_resolve_user_cache_hit(self, resolver, mock_slack_client):
        """Test resolve_user with cache hit."""
        # Pre-populate cache
        await resolver._cache.set("U123", "Alice")

        result = await resolver.resolve_user("U123")

        assert result == "Alice"
        mock_slack_client.users_info.assert_not_called()  # No API call

    @pytest.mark.asyncio
    async def test_resolve_user_api_call(self, resolver, mock_slack_client):
        """Test resolve_user with API call."""
        mock_slack_client.users_info.return_value = {
            "id": "U123",
            "name": "alice",
            "profile": {"display_name": "Alice", "real_name": "Alice Smith"},
        }

        result = await resolver.resolve_user("U123")

        assert result == "Alice"
        mock_slack_client.users_info.assert_called_once_with("U123")

        # Verify cached
        cached = await resolver._cache.get("U123")
        assert cached == "Alice"

    @pytest.mark.asyncio
    async def test_resolve_user_fallback_names(self, resolver, mock_slack_client):
        """Test name fallback: display_name > real_name > name."""
        # Test fallback to real_name
        mock_slack_client.users_info.return_value = {
            "id": "U123",
            "name": "alice",
            "profile": {"real_name": "Alice Smith"},
        }
        result = await resolver.resolve_user("U123")
        assert result == "Alice Smith"

        # Clear cache
        await resolver._cache.clear()

        # Test fallback to name
        mock_slack_client.users_info.return_value = {"id": "U456", "name": "bob"}
        result = await resolver.resolve_user("U456")
        assert result == "bob"

    @pytest.mark.asyncio
    async def test_resolve_user_empty_user_id(self, resolver, mock_slack_client):
        """Test resolve_user with empty user_id."""
        result = await resolver.resolve_user("")
        assert result is None
        mock_slack_client.users_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_user_api_failure(self, resolver, mock_slack_client):
        """Test resolve_user with API failure (negative caching)."""
        mock_slack_client.users_info.side_effect = Exception("API error")

        result = await resolver.resolve_user("U123")

        assert result is None
        mock_slack_client.users_info.assert_called_once_with("U123")

        # Verify negative result cached
        cached = await resolver._cache.get("U123")
        assert cached is None  # Cached None

        # Second call should not hit API (negative cache)
        result2 = await resolver.resolve_user("U123")
        assert result2 is None
        assert mock_slack_client.users_info.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_resolve_batch(self, resolver, mock_slack_client):
        """Test batch resolution with concurrency control."""
        mock_slack_client.users_info.side_effect = [
            {"profile": {"display_name": "Alice"}},
            {"profile": {"display_name": "Bob"}},
            {"profile": {"display_name": "Charlie"}},
        ]

        result = await resolver.resolve_batch(["U123", "U456", "U789"], max_concurrent=2)

        assert result == {"U123": "Alice", "U456": "Bob", "U789": "Charlie"}
        assert mock_slack_client.users_info.call_count == 3

    @pytest.mark.asyncio
    async def test_resolve_batch_deduplication(self, resolver, mock_slack_client):
        """Test batch deduplication."""
        mock_slack_client.users_info.return_value = {"profile": {"display_name": "Alice"}}

        result = await resolver.resolve_batch(["U123", "U123", "U123"])

        assert result == {"U123": "Alice"}
        mock_slack_client.users_info.assert_called_once()  # Only 1 call

    @pytest.mark.asyncio
    async def test_resolve_batch_empty_list(self, resolver, mock_slack_client):
        """Test batch resolution with empty list."""
        result = await resolver.resolve_batch([])
        assert result == {}
        mock_slack_client.users_info.assert_not_called()


@pytest.fixture
def mock_slack_channel():
    """Mock SlackChannel for mention annotation testing."""
    from app.channels.providers.slack.channel import SlackChannel

    channel = SlackChannel(bot_token="xoxb-test")
    channel._user_resolver = MagicMock()
    channel._user_resolver.resolve_batch = AsyncMock()
    return channel


class TestSlackMentionAnnotation:
    """Test Slack mention annotation in SlackChannel."""

    @pytest.mark.asyncio
    async def test_annotate_no_mentions(self, mock_slack_channel):
        """Test text without mentions is unchanged."""
        text = "Hello world, no mentions here"
        result = await mock_slack_channel._annotate_mentions(text)
        assert result == text
        mock_slack_channel._user_resolver.resolve_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_annotate_single_mention(self, mock_slack_channel):
        """Test single mention annotation."""
        mock_slack_channel._user_resolver.resolve_batch.return_value = {"U123": "Alice"}

        text = "<@U123> please review"
        result = await mock_slack_channel._annotate_mentions(text)

        assert result == "<@U123> (Alice) please review"
        mock_slack_channel._user_resolver.resolve_batch.assert_called_once_with(["U123"], max_concurrent=4)

    @pytest.mark.asyncio
    async def test_annotate_multiple_mentions(self, mock_slack_channel):
        """Test multiple mentions annotation."""
        mock_slack_channel._user_resolver.resolve_batch.return_value = {
            "U123": "Alice",
            "U456": "Bob",
            "U789": "Charlie",
        }

        text = "<@U123> and <@U456> and <@U789> please review"
        result = await mock_slack_channel._annotate_mentions(text)

        assert result == "<@U123> (Alice) and <@U456> (Bob) and <@U789> (Charlie) please review"

    @pytest.mark.asyncio
    async def test_annotate_duplicate_mentions(self, mock_slack_channel):
        """Test duplicate mentions are deduplicated."""
        mock_slack_channel._user_resolver.resolve_batch.return_value = {"U123": "Alice"}

        text = "<@U123> and <@U123> again"
        result = await mock_slack_channel._annotate_mentions(text)

        assert result == "<@U123> (Alice) and <@U123> (Alice) again"
        mock_slack_channel._user_resolver.resolve_batch.assert_called_once_with(["U123"], max_concurrent=4)

    @pytest.mark.asyncio
    async def test_annotate_mention_limit(self, mock_slack_channel):
        """Test mention limit (max 20)."""
        # Generate 25 unique mention IDs
        text = " ".join(f"<@U{i:03d}>" for i in range(25))

        mock_slack_channel._user_resolver.resolve_batch.return_value = {f"U{i:03d}": f"User{i}" for i in range(20)}

        await mock_slack_channel._annotate_mentions(text)

        # Only first 20 should be resolved
        call_args = mock_slack_channel._user_resolver.resolve_batch.call_args
        assert len(call_args[0][0]) == 20

    @pytest.mark.asyncio
    async def test_annotate_resolution_failure(self, mock_slack_channel):
        """Test mentions where resolution fails (keep original)."""
        mock_slack_channel._user_resolver.resolve_batch.return_value = {
            "U123": "Alice",
            "U456": None,  # Resolution failed
        }

        text = "<@U123> and <@U456> please review"
        result = await mock_slack_channel._annotate_mentions(text)

        assert result == "<@U123> (Alice) and <@U456> please review"

    @pytest.mark.asyncio
    async def test_annotate_empty_text(self, mock_slack_channel):
        """Test empty text handling."""
        result = await mock_slack_channel._annotate_mentions("")
        assert result == ""
        mock_slack_channel._user_resolver.resolve_batch.assert_not_called()


class TestSlackUserResolverMetrics:
    """Test OpenTelemetry metrics for SlackUserResolver."""

    @pytest.mark.asyncio
    async def test_metrics_cache_hit(self, mock_slack_client):
        """Test cache hit counter increments."""
        from unittest.mock import MagicMock

        resolver = SlackUserResolver(mock_slack_client, cache_ttl=60, cache_max_size=100)

        # Mock counters
        resolver._cache_hit_counter = MagicMock()
        resolver._cache_miss_counter = MagicMock()
        resolver._api_call_counter = MagicMock()
        resolver._api_failure_counter = MagicMock()

        mock_slack_client.users_info.return_value = {
            "profile": {"display_name": "Alice"},
        }

        # First call: cache miss, API call
        await resolver.resolve_user("U123")
        resolver._cache_hit_counter.add.assert_not_called()
        resolver._cache_miss_counter.add.assert_called_once_with(1)
        resolver._api_call_counter.add.assert_called_once_with(1)

        # Second call: cache hit
        resolver._cache_miss_counter.reset_mock()
        resolver._api_call_counter.reset_mock()
        await resolver.resolve_user("U123")
        resolver._cache_hit_counter.add.assert_called_once_with(1)
        resolver._cache_miss_counter.add.assert_not_called()
        resolver._api_call_counter.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_metrics_cache_miss(self, mock_slack_client):
        """Test cache miss counter increments."""
        from unittest.mock import MagicMock

        resolver = SlackUserResolver(mock_slack_client, cache_ttl=60, cache_max_size=100)

        # Mock counters
        resolver._cache_miss_counter = MagicMock()
        resolver._api_call_counter = MagicMock()

        mock_slack_client.users_info.return_value = {
            "profile": {"display_name": "Alice"},
        }

        await resolver.resolve_user("U123")

        resolver._cache_miss_counter.add.assert_called_once_with(1)
        resolver._api_call_counter.add.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_metrics_api_failure(self, mock_slack_client):
        """Test API failure counter increments."""
        from unittest.mock import MagicMock

        resolver = SlackUserResolver(mock_slack_client, cache_ttl=60, cache_max_size=100)

        # Mock counters
        resolver._cache_miss_counter = MagicMock()
        resolver._api_call_counter = MagicMock()
        resolver._api_failure_counter = MagicMock()

        mock_slack_client.users_info.side_effect = Exception("API error")

        await resolver.resolve_user("U123")

        resolver._cache_miss_counter.add.assert_called_once_with(1)
        resolver._api_call_counter.add.assert_called_once_with(1)
        resolver._api_failure_counter.add.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_metrics_negative_caching(self, mock_slack_client):
        """Test negative result is cached and counted as cache hit."""
        from unittest.mock import MagicMock

        resolver = SlackUserResolver(mock_slack_client, cache_ttl=60, cache_max_size=100)

        # Mock counters
        resolver._cache_hit_counter = MagicMock()
        resolver._cache_miss_counter = MagicMock()
        resolver._api_failure_counter = MagicMock()

        mock_slack_client.users_info.side_effect = Exception("API error")

        # First call: cache miss, API failure
        await resolver.resolve_user("U123")
        resolver._cache_hit_counter.add.assert_not_called()
        resolver._cache_miss_counter.add.assert_called_once_with(1)
        resolver._api_failure_counter.add.assert_called_once_with(1)

        # Second call: cache hit (negative result)
        resolver._cache_miss_counter.reset_mock()
        resolver._api_failure_counter.reset_mock()
        await resolver.resolve_user("U123")
        resolver._cache_hit_counter.add.assert_called_once_with(1)
        resolver._cache_miss_counter.add.assert_not_called()
        resolver._api_failure_counter.add.assert_not_called()  # No new API call

    @pytest.mark.asyncio
    async def test_metrics_eviction_counter(self, mock_slack_client):
        """Test cache eviction counter is incremented on LRU eviction."""
        from unittest.mock import MagicMock

        # Small cache to trigger eviction
        resolver = SlackUserResolver(mock_slack_client, cache_ttl=60, cache_max_size=2)

        # Mock eviction counter
        resolver._cache_eviction_counter = MagicMock()

        mock_slack_client.users_info.side_effect = lambda uid: {
            "ok": True,
            "user": {"id": uid, "profile": {"display_name": f"User{uid}"}},
        }

        # Fill cache (2 entries)
        await resolver.resolve_user("U001")
        await resolver.resolve_user("U002")
        resolver._cache_eviction_counter.add.assert_not_called()

        # Add 3rd entry, should trigger eviction
        await resolver.resolve_user("U003")
        resolver._cache_eviction_counter.add.assert_called_once_with(1)

        # Add 4th entry, another eviction
        resolver._cache_eviction_counter.reset_mock()
        await resolver.resolve_user("U004")
        resolver._cache_eviction_counter.add.assert_called_once_with(1)


class TestSlackChannelConfiguration:
    """Test configuration parameters for SlackChannel."""

    @pytest.fixture
    def mock_slack_channel_custom_config(self):
        """Mock SlackChannel with custom configuration."""
        from app.channels.providers.slack.channel import SlackChannel

        channel = SlackChannel(
            bot_token="xoxb-test",
            signing_secret="test_secret",
            user_resolver_cache_ttl=1800,
            user_resolver_cache_size=500,
            user_resolver_max_concurrent=8,
            mention_annotation_limit=10,
        )
        channel._user_resolver.resolve_batch = AsyncMock()
        return channel

    @pytest.mark.asyncio
    async def test_custom_mention_annotation_limit(self, mock_slack_channel_custom_config):
        """Test custom mention annotation limit is respected."""
        # Create text with 15 mentions
        text = " ".join(f"<@U{i:03d}>" for i in range(15))
        mock_slack_channel_custom_config._user_resolver.resolve_batch.return_value = {f"U{i:03d}": f"User{i}" for i in range(15)}

        await mock_slack_channel_custom_config._annotate_mentions(text)

        # Should limit to 10 (custom limit)
        call_args = mock_slack_channel_custom_config._user_resolver.resolve_batch.call_args
        assert len(call_args[0][0]) == 10

    @pytest.mark.asyncio
    async def test_custom_max_concurrent(self, mock_slack_channel_custom_config):
        """Test custom max_concurrent is passed to resolver."""
        text = "<@U123> <@U456>"
        mock_slack_channel_custom_config._user_resolver.resolve_batch.return_value = {
            "U123": "Alice",
            "U456": "Bob",
        }

        await mock_slack_channel_custom_config._annotate_mentions(text)

        # Should use custom max_concurrent=8
        call_args = mock_slack_channel_custom_config._user_resolver.resolve_batch.call_args
        assert call_args[1]["max_concurrent"] == 8
