"""A GitHub blob link is read as the file itself; every other URL is left as given.

The blob page wraps the file in a large HTML page that the HTTP tier cuts at its body ceiling, so a long source file
arrives as its first third. The rewrite keeps to github.com: GitHub redirects ``/raw/`` to the file, and the fetch judges
that redirect like any other.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.processing.github_blob_url import github_blob_to_raw

BLOB = "https://github.com/pallets/flask/blob/main/src/flask/app.py"
RAW = "https://github.com/pallets/flask/raw/main/src/flask/app.py"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param(BLOB, RAW, id="file-in-a-directory"),
        pytest.param(
            "https://github.com/psf/requests/blob/main/README.md",
            "https://github.com/psf/requests/raw/main/README.md",
            id="file-at-the-root",
        ),
        pytest.param(
            "https://github.com/acme/tool/blob/feature/x/docs/guide.md",
            "https://github.com/acme/tool/raw/feature/x/docs/guide.md",
            id="branch-name-with-a-slash",
        ),
        pytest.param(
            "https://github.com/acme/tool/blob/3f2a9c1d/src/a.py",
            "https://github.com/acme/tool/raw/3f2a9c1d/src/a.py",
            id="commit-hash",
        ),
        pytest.param(f"{BLOB}?plain=1#L10-L20", RAW, id="display-query-and-line-anchor-dropped"),
        pytest.param(
            "http://github.com/acme/tool/blob/main/a.py",
            "http://github.com/acme/tool/raw/main/a.py",
            id="scheme-kept",
        ),
        pytest.param(
            "https://GitHub.com/acme/tool/blob/main/a.py",
            "https://GitHub.com/acme/tool/raw/main/a.py",
            id="host-case-kept",
        ),
        pytest.param(
            "https://github.com/acme/tool/blob/main/dir%20x/a%2Bb.py",
            "https://github.com/acme/tool/raw/main/dir%20x/a%2Bb.py",
            id="percent-encoding-kept",
        ),
        pytest.param(
            "https://github.com/acme/tool/blob/main/blob/blob/a.py",
            "https://github.com/acme/tool/raw/main/blob/blob/a.py",
            id="only-the-marker-segment-changes",
        ),
    ],
)
def test_a_blob_page_becomes_its_raw_file(url: str, expected: str) -> None:
    assert github_blob_to_raw(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https://gitlab.com/acme/tool/blob/main/a.py", id="other-host"),
        pytest.param("https://www.github.com/acme/tool/blob/main/a.py", id="www-host"),
        pytest.param("https://github.example.com/acme/tool/blob/main/a.py", id="enterprise-host"),
        pytest.param("https://github.com.evil.example/acme/tool/blob/main/a.py", id="look-alike-host"),
        pytest.param("https://github.com@evil.example/acme/tool/blob/main/a.py", id="credentials-before-the-host"),
        pytest.param("https://github.com:8443/acme/tool/blob/main/a.py", id="explicit-port"),
        pytest.param("https://gist.github.com/acme/abc123/blob/main/a.py", id="gist-host"),
        pytest.param("https://raw.githubusercontent.com/acme/tool/main/a.py", id="raw-host"),
        pytest.param("https://github.com/acme/tool/raw/main/a.py", id="already-raw"),
        pytest.param("https://github.com/acme/tool/tree/main/src", id="tree"),
        pytest.param("https://github.com/acme/tool/blame/main/a.py", id="blame"),
        pytest.param("https://github.com/acme/tool/commit/3f2a9c1d", id="commit"),
        pytest.param("https://github.com/acme/tool", id="repository-root"),
        pytest.param("https://github.com/acme/tool/blob/main", id="blob-without-a-path"),
        pytest.param("https://github.com/acme/tool/blob/main/", id="blob-ending-in-a-slash"),
        pytest.param("https://github.com/acme/tool/blob//a.py", id="empty-segment"),
        pytest.param("https://github.com/acme/tool/Blob/main/a.py", id="marker-in-another-case"),
        pytest.param("https://github.com/acme/blob/issues/42/files", id="repository-named-blob"),
        pytest.param("ftp://github.com/acme/tool/blob/main/a.py", id="other-scheme"),
        pytest.param("", id="empty-string"),
        pytest.param("not a url", id="not-a-url"),
    ],
)
def test_anything_else_is_returned_unchanged(url: str) -> None:
    assert github_blob_to_raw(url) == url


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[FetchEngine]:
    # Private networks are allowed only so that the SSRF lookup, which these tests are not about, needs no network.
    fetch_engine = FetchEngine(allow_private_networks=True)
    yield fetch_engine
    await fetch_engine.shutdown()


@pytest.fixture
def network() -> AsyncMock:
    """The tier ladder, answering every URL with a document."""
    with patch.object(FetchEngine, "_crawl_with_degradation", new_callable=AsyncMock) as ladder:
        ladder.return_value = (Document(page_content="source", metadata={}), None)
        yield ladder


@pytest.mark.asyncio
async def test_crawl_requests_the_raw_file_of_a_blob_link(engine: FetchEngine, network: AsyncMock) -> None:
    assert await engine.crawl(f"{BLOB}?plain=1#L10") is not None

    network.assert_awaited_once()
    assert network.await_args is not None
    assert network.await_args.args[0] == RAW


@pytest.mark.asyncio
async def test_a_blob_link_and_a_raw_link_to_the_same_file_share_one_fetch(
    engine: FetchEngine, network: AsyncMock
) -> None:
    await engine.crawl(BLOB)
    await engine.crawl(RAW)

    assert network.await_count == 1


@pytest.mark.asyncio
async def test_crawl_leaves_other_urls_as_given(engine: FetchEngine, network: AsyncMock) -> None:
    other = "https://gitlab.com/acme/tool/blob/main/a.py"

    await engine.crawl(other)

    assert network.await_args is not None
    assert network.await_args.args[0] == other


@pytest.mark.asyncio
async def test_a_listed_github_host_is_refused_before_the_rewrite(network: AsyncMock) -> None:
    listed = FetchEngine(allow_private_networks=True, network_blocklist=("github.com",))
    try:
        assert await listed.crawl(BLOB) is None
    finally:
        await listed.shutdown()

    network.assert_not_awaited()
