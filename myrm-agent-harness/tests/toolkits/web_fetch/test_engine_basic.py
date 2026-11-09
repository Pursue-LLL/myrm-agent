"""FetchEngine 基础功能测试（不涉及实际网络请求）"""

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine


@pytest.mark.asyncio
async def test_engine_initialization_defaults():
    """测试引擎默认初始化"""
    engine = FetchEngine()

    assert engine._http_fetcher is not None
    assert engine._browser_fetcher is not None
    assert engine._stealth_fetcher is not None
    assert engine._tier_breaker is not None
    assert engine._domain_metrics is not None
    assert engine._pipeline is not None
    assert engine._crawl_cache is not None
    assert engine._fail_cache is not None

    await engine.shutdown()


@pytest.mark.asyncio
async def test_engine_custom_config():
    """测试引擎自定义配置"""
    engine = FetchEngine(
        use_raw_markdown=True,
        cache_ttl=1800,
        cache_maxsize=1000,
        cache_max_bytes=50 * 1024 * 1024,
    )

    assert engine._crawl_cache.ttl == 1800
    assert engine._crawl_cache.maxsize == 1000

    await engine.shutdown()


@pytest.mark.asyncio
async def test_engines_share_the_process_wide_tier_breaker():
    """每次调用新建的引擎共用同一个熔断器，域名学到的层级不随引擎消失"""
    first, second = FetchEngine(), FetchEngine()

    assert first._tier_breaker is second._tier_breaker
    assert first._domain_metrics is second._domain_metrics

    await first.shutdown()
    await second.shutdown()


@pytest.mark.asyncio
async def test_get_cache_metrics():
    """测试获取缓存指标"""
    engine = FetchEngine()

    metrics = engine.get_cache_metrics()

    assert "crawl_cache" in metrics
    assert "fail_cache" in metrics

    await engine.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
