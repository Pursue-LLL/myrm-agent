"""Real-Chromium proof that a long response body stays readable through network_detail and the vault.

The page fetches a body of a few hundred thousand characters, minified onto one line. network_detail answers with where
all of it is and the start of it; the vault copy is masked, wrapped into short lines and read by line range exactly as
file_read reads it; and the server is asked once, because the body comes from Chrome's own cache.
Run with: `pytest -m integration tests/toolkits/browser/session/test_network_detail_long_body_integration.py`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import ViewRange
from myrm_agent_harness.agent.meta_tools.file_ops.utils.vault_read import read_vault_text_content
from myrm_agent_harness.toolkits.browser import BrowserSession
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._local_browser_session import local_session
from tests.toolkits.browser._redirect_servers import Reply, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_ROWS = 3000
_PASSWORD = "mysecretvalue12345678"
_GOOGLE_KEY = "AIza" + "S" * 35
_POINTER = re.compile(r"vault://[a-f0-9-]+")
_BODY_READ_TIMEOUT_MS = 10_000


def _big_body() -> str:
    rows = [{"id": n, "name": f"item-{n:05d}", "url": f"https://cdn.example.com/p/{n:05d}.jpg"} for n in range(_ROWS)]
    rows[1500]["password"] = _PASSWORD
    rows[2500]["link"] = f"https://maps.example.com/embed?k={_GOOGLE_KEY}&z=1"
    return json.dumps(rows, separators=(",", ":"))


async def _fetch_the_big_body(session: BrowserSession, site_url: Callable[[str], str]) -> None:
    """Open the page and wait until it has read the whole body, so the browser has finished receiving it."""
    await session.navigate(site_url("/app"))
    await session._tab_controller.get_active_page().wait_for_function(
        "window.bodyRead === true", timeout=_BODY_READ_TIMEOUT_MS
    )


def _pointer(answer: str) -> str:
    match = _POINTER.search(answer)
    assert match, f"the answer names no vault object: {answer[-300:]!r}"
    return match.group(0)


def _routes(body: str) -> dict[str, Reply]:
    page = (
        "<!DOCTYPE html><html><body>app<script>"
        "fetch('/api/big').then(r => r.text()).then(() => { window.bodyRead = true })"
        "</script></body></html>"
    )
    return {"/app": Reply(body=page.encode()), "/api/big": Reply(body=body.encode(), content_type="application/json")}


async def test_a_long_body_is_kept_in_full_in_the_vault_masked_and_wrapped(tmp_path: Path) -> None:
    body = _big_body()
    with serve(_routes(body)) as site:
        async with local_session(content_vault=ArtifactVault(str(tmp_path))) as session:
            await _fetch_the_big_body(session, site.url)

            answer = await session.get_network_detail(1)

            pointer = _pointer(answer)
            header, preview = answer.split("\n", 1)
            assert header == (
                f"[Response body: {len(body)} chars, saved in full to {pointer} (read it with file_read; "
                "lines wrapped at 200 chars). MIME: application/json. First 8000 chars:]"
            )
            assert preview == body[:8000]
            copy = ArtifactVault(str(tmp_path)).get(pointer).decode()
            lines = copy.split("\n")
            assert max(len(line) for line in lines) <= 200
            assert f"item-{_ROWS - 1:05d}" in copy
            assert _PASSWORD not in copy
            assert _GOOGLE_KEY not in copy
            assert "AIzaSSSSSSSS" not in copy
            assert copy.replace("\n", "")[:8000] == preview
            assert site.paths("GET").count("/api/big") == 1


async def test_a_line_range_of_the_copy_reads_the_part_the_answer_did_not_show(tmp_path: Path) -> None:
    body = _big_body()
    with serve(_routes(body)) as site:
        async with local_session(content_vault=ArtifactVault(str(tmp_path))) as session:
            await _fetch_the_big_body(session, site.url)
            answer = await session.get_network_detail(1)

            pointer = _pointer(answer)
            page = read_vault_text_content(pointer, str(tmp_path), view_range=ViewRange(start=500, end=502))

            assert page == "".join(f"{body[start : start + 200]}\n" for start in (499 * 200, 500 * 200, 501 * 200))
            assert page not in answer


async def test_without_a_vault_the_answer_is_the_masked_start_and_the_length() -> None:
    body = _big_body()
    with serve(_routes(body)) as site:
        async with local_session() as session:
            await _fetch_the_big_body(session, site.url)

            answer = await session.get_network_detail(1)

            assert answer == f"{body[:8000]}\n\n... [truncated, total {len(body)} chars] MIME: application/json"
