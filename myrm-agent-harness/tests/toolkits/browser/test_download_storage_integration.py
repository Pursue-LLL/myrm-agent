"""Real-Chromium proof that downloads are kept under their own names, within a quota, and fetched again when asked again.

Downloads that save at the same moment each get a file of their own and keep their own content; a directory that is
full keeps no more files, says why, and names the way out; the directory appears with the first download and ignores
itself in version control; asking for a URL again asks the server again, so a file that changed is not mistaken for the
one saved before; and download requests on one page take turns, each getting the download it started. The hosts are
fake (see ``test_download_url_integration``).
Run with: `pytest -m integration tests/toolkits/browser/test_download_storage_integration.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._download_doubles import kept_files
from tests.toolkits.browser._download_integration import (
    DNS_ANSWERS,
    SETTLE_S,
    attachment,
    kept_by_browser_once_settled,
    open_session,
    point_browser_tmpdir,
    until,
)
from tests.toolkits.browser._fake_dns import process_dns, url_on
from tests.toolkits.browser._redirect_servers import Reply, page, serve

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.session import BrowserSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

# One script starts every download, each by a link of the page's own origin, so they are under way together.
_START_DOWNLOADS_JS = """(urls) => {
    for (const url of urls) {
        const link = document.createElement('a');
        link.href = url;
        link.download = '';
        document.body.appendChild(link);
        link.click();
    }
}"""
_BURST = 5


def _accounted_for(session: BrowserSession, count: int) -> bool:
    """Whether ``count`` downloads of the session have been saved or refused."""
    return len(session.list_downloads()) + len(session.download_refusals) == count


@pytest.fixture(autouse=True)
def _process_dns() -> Iterator[None]:
    with process_dns(DNS_ANSWERS):
        yield


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    return tmp_path / "workspace" / ".agent" / "downloads"


@pytest.fixture
def browser_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return point_browser_tmpdir(tmp_path, monkeypatch)


class TestNamesAndQuota:
    async def test_downloads_saving_at_the_same_moment_keep_their_own_content(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        routes: dict[str, Reply] = {"/home": page("home")}
        routes.update({f"/f{n}": attachment("report.txt", f"body-{n}".encode()) for n in range(_BURST)})
        with serve(routes) as site:
            async with open_session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await session.get_active_page().evaluate(
                    _START_DOWNLOADS_JS, [url_on("public.test", site, f"/f{n}") for n in range(_BURST)]
                )
                await until(lambda: len(session.list_downloads()) == _BURST)

                assert sorted(Path(saved.path).read_bytes() for saved in session.list_downloads()) == [
                    f"body-{n}".encode() for n in range(_BURST)
                ]
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == [
                "report (1).txt",
                "report (2).txt",
                "report (3).txt",
                "report (4).txt",
                "report.txt",
            ]

    async def test_a_full_directory_refuses_more_files_and_the_agent_is_told_why(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        with serve({"/home": page("home"), **{f"/f{n}": attachment(f"f{n}.txt", b"x") for n in range(3)}}) as site:
            async with open_session(downloads_dir, local=False, max_files=2) as session:
                await session.navigate(url_on("public.test", site, "/home"))
                assert not downloads_dir.exists()  # a workspace that has not downloaded has no downloads folder

                for n in range(3):
                    await session.get_active_page().evaluate(
                        _START_DOWNLOADS_JS, [url_on("public.test", site, f"/f{n}")]
                    )
                    await until(partial(_accounted_for, session, n + 1))

                (refusal,) = session.download_refusals
                assert refusal.file_name == "f2.txt"
                assert "folder is full" in refusal.reason
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == ["f0.txt", "f1.txt"]
            assert (downloads_dir / ".gitignore").read_text(encoding="utf-8") == "*\n"


class TestAskingAgain:
    async def test_a_url_asked_for_again_is_asked_of_the_server_again(self, downloads_dir: Path) -> None:
        routes = {"/home": page("home"), "/file": attachment("a.txt", b"v1")}
        with serve(routes) as site:
            async with open_session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))
                url = url_on("public.test", site, "/file")

                first = await session.download_url(url)
                routes["/file"] = attachment("a.txt", b"v2")
                second = await session.download_url(url)

                assert (Path(first.path).read_bytes(), Path(second.path).read_bytes()) == (b"v1", b"v2")
                assert (first.file_name, second.file_name) == ("a.txt", "a (1).txt")
            assert site.paths().count("/file") == 2


class TestRequestsOnOnePage:
    async def test_requests_made_together_each_get_the_file_they_asked_for(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        routes = {
            "/home": page("home"),
            "/a": attachment(
                "a.txt",
                b"AAA",
            ),
            "/b": attachment("b.txt", b"BBB"),
        }
        with serve(routes) as site:
            async with open_session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                first, second = await asyncio.gather(
                    session.download_url(url_on("public.test", site, "/a")),
                    session.download_url(url_on("public.test", site, "/b")),
                )
                await asyncio.sleep(SETTLE_S)

                assert (first.file_name, Path(first.path).read_bytes()) == ("a.txt", b"AAA")
                assert (second.file_name, Path(second.path).read_bytes()) == ("b.txt", b"BBB")
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == ["a.txt", "b.txt"]
