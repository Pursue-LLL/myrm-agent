"""CancellationToken TTL cleanup scheduler tests.

Verifies:
1. CancellationRegistry.cleanup_expired() correctly removes stale tokens
2. Active tokens survive cleanup
3. The scheduler job function works end-to-end
"""

import time

import pytest
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationRegistry,
    CancellationToken,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure registry is clean before/after each test."""
    CancellationRegistry._tokens.clear()
    yield
    CancellationRegistry._tokens.clear()


class TestCancellationRegistryCleanup:
    def test_cleanup_removes_expired_tokens(self) -> None:
        old_token = CancellationToken(request_id="old-req")
        old_token._created_at = time.time() - 7200

        CancellationRegistry.register(old_token)
        assert CancellationRegistry.get_active_count() == 1

        removed = CancellationRegistry.cleanup_expired(ttl_seconds=3600)

        assert removed == 1
        assert CancellationRegistry.get_active_count() == 0

    def test_cleanup_preserves_active_tokens(self) -> None:
        active_token = CancellationToken(request_id="active-req")

        CancellationRegistry.register(active_token)
        assert CancellationRegistry.get_active_count() == 1

        removed = CancellationRegistry.cleanup_expired(ttl_seconds=3600)

        assert removed == 0
        assert CancellationRegistry.get_active_count() == 1

    def test_cleanup_mixed_tokens(self) -> None:
        expired1 = CancellationToken(request_id="expired-1")
        expired1._created_at = time.time() - 7200

        expired2 = CancellationToken(request_id="expired-2")
        expired2._created_at = time.time() - 5000

        active1 = CancellationToken(request_id="active-1")
        active2 = CancellationToken(request_id="active-2")

        for t in [expired1, expired2, active1, active2]:
            CancellationRegistry.register(t)

        assert CancellationRegistry.get_active_count() == 4

        removed = CancellationRegistry.cleanup_expired(ttl_seconds=3600)

        assert removed == 2
        assert CancellationRegistry.get_active_count() == 2
        assert CancellationRegistry.cancel("active-1")
        assert CancellationRegistry.cancel("active-2")
        assert not CancellationRegistry.cancel("expired-1")
        assert not CancellationRegistry.cancel("expired-2")

    def test_cleanup_empty_registry(self) -> None:
        removed = CancellationRegistry.cleanup_expired(ttl_seconds=3600)
        assert removed == 0

    def test_register_unregister_symmetry(self) -> None:
        token = CancellationToken(request_id="sym-req")
        CancellationRegistry.register(token)
        assert CancellationRegistry.get_active_count() == 1

        CancellationRegistry.unregister("sym-req")
        assert CancellationRegistry.get_active_count() == 0

        removed = CancellationRegistry.cleanup_expired(ttl_seconds=0)
        assert removed == 0


class TestCancellationCleanupJob:
    @pytest.mark.asyncio
    async def test_cleanup_job_function(self) -> None:
        from app.lifecycle.schedulers import _cancellation_token_cleanup_job

        old_token = CancellationToken(request_id="job-test-old")
        old_token._created_at = time.time() - 7200
        CancellationRegistry.register(old_token)

        active_token = CancellationToken(request_id="job-test-active")
        CancellationRegistry.register(active_token)

        assert CancellationRegistry.get_active_count() == 2

        await _cancellation_token_cleanup_job()

        assert CancellationRegistry.get_active_count() == 1
        assert CancellationRegistry.cancel("job-test-active")
        assert not CancellationRegistry.cancel("job-test-old")
