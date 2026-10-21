"""Tests for per-channel token bucket rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.channels.reliability.rate_limiter import TokenBucket, create_limiter


@pytest.mark.asyncio
async def test_burst_tokens_available_immediately() -> None:
    bucket = TokenBucket(rate=10.0, burst=5)
    for _ in range(5):
        await bucket.acquire()


@pytest.mark.asyncio
async def test_blocks_after_burst_exhausted() -> None:
    bucket = TokenBucket(rate=100.0, burst=1)
    await bucket.acquire()

    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.001  # should wait ~0.01s at 100/s


@pytest.mark.asyncio
async def test_tokens_refill_over_time() -> None:
    bucket = TokenBucket(rate=1000.0, burst=2)
    await bucket.acquire()
    await bucket.acquire()

    await asyncio.sleep(0.01)
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


def test_create_limiter_whatsapp() -> None:
    limiter = create_limiter("whatsapp")
    assert limiter._rate == 2.0
    assert limiter._burst == 1


def test_create_limiter_telegram() -> None:
    limiter = create_limiter("telegram")
    assert limiter._rate == 20.0
    assert limiter._burst == 10


def test_create_limiter_wechat() -> None:
    limiter = create_limiter("wechat")
    assert limiter._rate == 2.0
    assert limiter._burst == 1


def test_create_limiter_wechat_official() -> None:
    limiter = create_limiter("wechat_official")
    assert limiter._rate == 1.0
    assert limiter._burst == 1


def test_create_limiter_default() -> None:
    limiter = create_limiter("unknown_channel")
    assert limiter._rate == 10.0
    assert limiter._burst == 5
