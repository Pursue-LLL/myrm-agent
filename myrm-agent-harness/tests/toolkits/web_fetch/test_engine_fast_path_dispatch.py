"""``FetchEngine.crawl`` tries a platform's fast path first and falls back to the tier ladder.

For YouTube, Bilibili, WeChat and X the same contract holds: a hit skips the ladder and is cached, a miss goes down the
ladder exactly once with the caller's arguments and the cached validators, each stage has its own crawl timeout, and a
failing fast path never reaches the ladder. The extractors and the ladder are faked; the engine's dispatch, timeouts,
caches and logging run for real.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, create_autospec, patch

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.browser.pool.proxy import ProxyPool
from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.engine.types import CachedDocument
from myrm_agent_harness.toolkits.web_fetch.processing.url_normalizer import normalize_url

# The module whose names the dispatch looks the platform extractors up in.
_DISPATCH = "myrm_agent_harness.toolkits.web_fetch.engine.base"
_CAP_S = 0.2
# A hang is cut off by this guard, so a missing timeout fails a test instead of hanging the run.
_GUARD_S = 5.0
_COOKIES = {"SESSDATA": "s"}
_LANGUAGES = ["zh-Hans"]
_PROXY_POOL = create_autospec(ProxyPool, instance=True)
_PLAIN_URL = "https://example.com/article"

Fake = Callable[..., Awaitable[object]]


@dataclass(frozen=True)
class Platform:
    name: str
    url: str
    extractor: str
    # What the engine passes to the extractor besides the URL and the proxy pool.
    extractor_kwargs: dict[str, object] = field(default_factory=dict)


PLATFORMS = (
    Platform(
        "youtube",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "extract_youtube_transcript",
        {"preferred_languages": _LANGUAGES},
    ),
    Platform(
        "bilibili", "https://www.bilibili.com/video/BV1xx411c7mD", "extract_bilibili_subtitle", {"cookies": _COOKIES}
    ),
    Platform("wechat", "https://mp.weixin.qq.com/s/abc123", "extract_weixin_article"),
    Platform("x", "https://x.com/someone/status/1234567890", "extract_x_post"),
)


def page(text: str) -> Document:
    return Document(page_content=text, metadata={})


async def hang(*_args: object, **_kwargs: object) -> None:
    await asyncio.sleep(3600)


@asynccontextmanager
async def running_engine(*, cache_ttl: int = 3600, stale_while_revalidate: bool = True) -> AsyncIterator[FetchEngine]:
    # SSRF policy is not under test; allowing private networks keeps the fake hosts from needing a DNS lookup.
    fetch_engine = FetchEngine(
        allow_private_networks=True,
        crawl_timeout=_CAP_S,
        cache_ttl=cache_ttl,
        stale_while_revalidate=stale_while_revalidate,
        youtube_languages=_LANGUAGES,
        proxy_pool=_PROXY_POOL,
    )
    with patch.object(fetch_engine, "_load_bilibili_cookies", new=AsyncMock(return_value=_COOKIES)):
        try:
            yield fetch_engine
        finally:
            await fetch_engine.shutdown()


@contextmanager
def faked(engine: FetchEngine, extractor: str, fast_path: Fake, ladder: Fake) -> Iterator[None]:
    with patch(f"{_DISPATCH}.{extractor}", new=fast_path), patch.object(engine, "_crawl_with_degradation", new=ladder):
        yield


@pytest.fixture
async def engine() -> AsyncIterator[FetchEngine]:
    async with running_engine() as fetch_engine:
        yield fetch_engine


@pytest.fixture(params=PLATFORMS, ids=lambda platform: platform.name)
def platform(request: pytest.FixtureRequest) -> Platform:
    return request.param


async def test_a_hit_skips_the_ladder_and_is_cached(engine: FetchEngine, platform: Platform) -> None:
    fast_path = AsyncMock(return_value=page("fast"))
    ladder = AsyncMock(return_value=(page("ladder"), None))

    with faked(engine, platform.extractor, fast_path, ladder):
        first = await engine.crawl(platform.url)
        second = await engine.crawl(platform.url)

    assert first is not None and first.page_content == "fast"
    assert second is not None and second.page_content == "fast"
    fast_path.assert_awaited_once()  # the second crawl is a cache hit
    assert fast_path.await_args.args == (platform.url,)
    assert fast_path.await_args.kwargs == {**platform.extractor_kwargs, "proxy_pool": _PROXY_POOL}
    ladder.assert_not_awaited()


async def test_a_miss_goes_down_the_ladder_once_with_the_callers_arguments(
    engine: FetchEngine, platform: Platform
) -> None:
    fast_path = AsyncMock(return_value=None)
    ladder = AsyncMock(return_value=(page("ladder"), None))

    with faked(engine, platform.extractor, fast_path, ladder):
        result = await engine.crawl(platform.url, max_chars=777, allow_escalation=False)

    assert result is not None and result.page_content == "ladder"
    fast_path.assert_awaited_once()
    ladder.assert_awaited_once()
    assert ladder.await_args.args == (platform.url,)
    assert ladder.await_args.kwargs == {
        "etag": None,
        "last_modified": None,
        "max_chars": 777,
        "allow_escalation": False,
    }


async def test_each_stage_has_its_own_crawl_timeout(engine: FetchEngine, platform: Platform) -> None:
    async def slow_miss(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(_CAP_S * 0.6)

    with faked(engine, platform.extractor, slow_miss, hang):
        started = time.monotonic()
        async with asyncio.timeout(_GUARD_S):
            result = await engine.crawl(platform.url)
        elapsed = time.monotonic() - started

    assert result is None
    # One cap shared by both stages would end the crawl at _CAP_S; a cap per stage ends it at 1.6 caps.
    assert elapsed >= _CAP_S * 1.3


async def test_a_fast_path_that_times_out_ends_the_crawl_without_the_ladder(
    engine: FetchEngine, platform: Platform
) -> None:
    ladder = AsyncMock(return_value=(page("ladder"), None))

    with faked(engine, platform.extractor, hang, ladder):
        async with asyncio.timeout(_GUARD_S):
            result = await engine.crawl(platform.url)

    assert result is None
    ladder.assert_not_awaited()
    assert engine._fail_cache.contains(normalize_url(platform.url))


@pytest.mark.parametrize(
    ("error", "propagates"), [(RuntimeError("extractor broke"), True), (ConnectionError("down"), False)]
)
async def test_a_failing_fast_path_never_reaches_the_ladder(
    engine: FetchEngine, platform: Platform, error: Exception, propagates: bool
) -> None:
    ladder = AsyncMock(return_value=(page("ladder"), None))

    with faked(engine, platform.extractor, AsyncMock(side_effect=error), ladder):
        if propagates:
            with pytest.raises(type(error), match="extractor broke"):
                await engine.crawl(platform.url)
        else:
            assert await engine.crawl(platform.url) is None

    ladder.assert_not_awaited()


async def test_a_url_without_a_fast_path_goes_straight_to_the_ladder(engine: FetchEngine) -> None:
    extractors = {platform.extractor: AsyncMock(return_value=page("fast")) for platform in PLATFORMS}
    ladder = AsyncMock(return_value=(page("ladder"), None))

    with ExitStack() as patches:
        for name, extractor in extractors.items():
            patches.enter_context(patch(f"{_DISPATCH}.{name}", new=extractor))
        patches.enter_context(patch.object(engine, "_crawl_with_degradation", new=ladder))
        result = await engine.crawl(_PLAIN_URL)

    assert result is not None and result.page_content == "ladder"
    assert all(extractor.await_count == 0 for extractor in extractors.values())
    ladder.assert_awaited_once()


@pytest.mark.parametrize(
    ("platform_name", "fast_page", "ladder_page", "logged"),
    [
        ("wechat", page("w"), None, ["Weixin article fast-path succeeded"]),
        (
            "wechat",
            None,
            page("l"),
            ["Weixin article fast-path missed, degrading to browser", "Weixin article browser degradation succeeded"],
        ),
        (
            "wechat",
            None,
            None,
            ["Weixin article fast-path missed, degrading to browser", "Weixin article fetch failed after degradation"],
        ),
        ("x", page("x"), None, ["Twitter/X post fast-path succeeded"]),
        ("x", None, page("l"), ["Twitter/X post fast-path missed, degrading to standard fetch"]),
    ],
    ids=["wechat-hit", "wechat-miss-served", "wechat-miss-failed", "x-hit", "x-miss"],
)
async def test_wechat_and_x_log_which_path_served_the_url(
    engine: FetchEngine,
    caplog: pytest.LogCaptureFixture,
    platform_name: str,
    fast_page: Document | None,
    ladder_page: Document | None,
    logged: list[str],
) -> None:
    target = next(candidate for candidate in PLATFORMS if candidate.name == platform_name)
    caplog.set_level(logging.INFO, logger=_DISPATCH)

    with faked(
        engine, target.extractor, AsyncMock(return_value=fast_page), AsyncMock(return_value=(ladder_page, None))
    ):
        await engine.crawl(target.url)

    messages = [record.getMessage() for record in caplog.records if record.name == _DISPATCH]
    for fragment in logged:
        assert any(fragment in message for message in messages), (fragment, messages)
    absent = ["fast-path succeeded"] if fast_page is None else ["fast-path missed", "degradation"]
    for fragment in absent:
        assert not any(fragment in message for message in messages), (fragment, messages)


async def test_a_miss_passes_the_validators_of_an_expired_entry_to_the_ladder() -> None:
    # One engine per platform, so one wait covers them all: the first miss to fill a cache would otherwise purge the
    # other expired entries of that cache.
    async with AsyncExitStack() as stack:
        engines = [
            (
                platform,
                await stack.enter_async_context(running_engine(cache_ttl=1, stale_while_revalidate=False)),
            )
            for platform in PLATFORMS
        ]
        for platform, engine in engines:
            stale = CachedDocument(
                doc=page("old"), etag=f"etag-{platform.name}", last_modified="Mon", cached_at=time.time()
            )
            engine._crawl_cache.set(normalize_url(platform.url), stale)
        await asyncio.sleep(1.1)  # the cache's ttl is whole seconds

        for platform, engine in engines:
            ladder = AsyncMock(return_value=(page("new"), None))
            with faked(engine, platform.extractor, AsyncMock(return_value=None), ladder):
                result = await engine.crawl(platform.url)

            assert result is not None and result.page_content == "new"
            assert ladder.await_args.kwargs["etag"] == f"etag-{platform.name}"
            assert ladder.await_args.kwargs["last_modified"] == "Mon"
