"""测试 URL 规范化功能"""

from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.processing.url_normalizer import normalize_url


def test_remove_tracking_params():
    """测试移除追踪参数"""
    url = "https://example.com/page?utm_source=google&utm_medium=cpc&id=123"
    normalized = normalize_url(url)
    assert "utm_source" not in normalized
    assert "utm_medium" not in normalized
    assert "id=123" in normalized


def test_remove_extended_tracking_params():
    """测试移除扩展的追踪参数（HubSpot, LinkedIn, TikTok 等）"""
    test_cases = [
        ("https://example.com?_hsenc=abc&_hsmi=123&id=1", "id=1"),
        ("https://example.com?li_fat_id=xyz&li_source=test&id=2", "id=2"),
        ("https://example.com?ttclid=tiktok&twclid=twitter&id=3", "id=3"),
        ("https://example.com?s_cid=adobe&_gid=ga&id=4", "id=4"),
        ("https://example.com?fbclid=fb&gclid=google&msclkid=bing&id=5", "id=5"),
    ]

    for url, expected_param in test_cases:
        normalized = normalize_url(url)
        assert expected_param in normalized
        assert "hsenc" not in normalized
        assert "li_fat_id" not in normalized
        assert "ttclid" not in normalized
        assert "s_cid" not in normalized


def test_lowercase_scheme_and_netloc():
    """测试统一 scheme 和 netloc 为小写"""
    url = "HTTPS://EXAMPLE.COM/Page"
    normalized = normalize_url(url)
    assert normalized.startswith("https://example.com/")


def test_remove_default_ports():
    """测试移除默认端口"""
    assert normalize_url("http://example.com:80/page") == "http://example.com/page"
    assert normalize_url("https://example.com:443/page") == "https://example.com/page"
    assert normalize_url("http://example.com:8080/page") == "http://example.com:8080/page"


def test_normalize_path():
    """测试规范化路径（移除多余斜杠）"""
    url = "https://example.com//path//to///page"
    normalized = normalize_url(url)
    assert "/path/to/page" in normalized


def test_sort_query_params():
    """测试查询参数按字母排序"""
    url = "https://example.com/page?z=3&a=1&m=2"
    normalized = normalize_url(url)
    assert normalized == "https://example.com/page?a=1&m=2&z=3"


def test_complex_url():
    """测试复杂 URL 规范化"""
    url = "HTTPS://Example.COM:443//path//to/page?utm_source=fb&z=3&a=1&fbclid=xyz"
    normalized = normalize_url(url)

    assert normalized.startswith("https://example.com/")
    assert "utm_source" not in normalized
    assert "fbclid" not in normalized
    assert "a=1" in normalized
    assert "z=3" in normalized
    assert normalized.index("a=1") < normalized.index("z=3")


def test_url_without_query():
    """测试没有查询参数的 URL"""
    url = "https://example.com/page"
    normalized = normalize_url(url)
    assert normalized == "https://example.com/page"


def test_url_with_fragment():
    """普通锚点不改变页面内容，不进缓存键"""
    url = "https://example.com/page#section"
    normalized = normalize_url(url)
    assert "#section" not in normalized
    assert normalized == normalize_url("https://example.com/page")
    assert normalize_url("https://example.com/page?a=1#top") == normalize_url("https://example.com/page?a=1")


@pytest.mark.parametrize("prefix", ["/", "!/"])
def test_hash_route_fragments_are_distinct_keys(prefix: str):
    """哈希路由页面的不同路由是不同的页面，不能共用缓存键"""
    alpha = normalize_url(f"https://example.com/app#{prefix}alpha")
    beta = normalize_url(f"https://example.com/app#{prefix}beta")
    assert alpha != beta
    assert alpha.endswith(f"#{prefix}alpha")
    assert alpha != normalize_url("https://example.com/app")


def test_hash_route_still_drops_tracking_params():
    """保留路由片段不影响追踪参数的剥离"""
    assert normalize_url("https://example.com/app?utm_source=x&b=2&a=1#/inbox") == (
        "https://example.com/app?a=1&b=2#/inbox"
    )


@pytest.mark.parametrize("name", ["ref", "referrer", "source"])
def test_generic_parameter_names_select_content(name: str):
    """ref、referrer、source 可能选择内容（GitHub contents API 的 ?ref= 选分支），不能当追踪参数丢弃"""
    base = "https://api.github.com/repos/owner/repo/contents/setup.py"
    assert normalize_url(f"{base}?{name}=3.12") != normalize_url(f"{base}?{name}=3.13")
    assert normalize_url(f"{base}?{name}=3.12") != normalize_url(base)
    assert normalize_url(f"{base}?{name}=3.12") == f"{base}?{name}=3.12"


@pytest.mark.parametrize(
    "url1,url2",
    [
        ("https://example.com/page?utm_source=a", "https://example.com/page"),
        ("HTTPS://EXAMPLE.COM/page", "https://example.com/page"),
        ("https://example.com:443/page", "https://example.com/page"),
        ("https://example.com/page?z=1&a=2", "https://example.com/page?a=2&z=1"),
    ],
)
def test_equivalent_urls_normalized_to_same(url1: str, url2: str):
    """测试等价 URL 规范化为相同结果"""
    assert normalize_url(url1) == normalize_url(url2)


async def test_engine_fetches_each_content_selecting_url_separately():
    """引擎层回归：`?ref=` 不同值、哈希路由不同路由各抓一次，第二个请求拿不到第一个的内容"""
    urls = [
        "https://page.example/contents?ref=3.12",
        "https://page.example/contents?ref=3.13",
        "https://page.example/app#/alpha",
        "https://page.example/app#/beta",
    ]

    async def fetch(url: str, **_: object) -> tuple[Document, None]:
        return Document(page_content=url, metadata={}), None

    # The SSRF policy is not under test; allowing private networks keeps the fake host from needing a DNS lookup.
    engine = FetchEngine(allow_private_networks=True)
    network = AsyncMock(side_effect=fetch)
    engine._crawl_with_degradation = network  # type: ignore[method-assign]
    try:
        pages = [await engine.crawl(url) for url in urls]
        repeat = await engine.crawl(urls[0])
    finally:
        await engine.shutdown()

    assert [page.page_content for page in pages if page is not None] == urls
    assert repeat is not None
    assert repeat.page_content == urls[0]
    assert network.call_count == len(urls)
