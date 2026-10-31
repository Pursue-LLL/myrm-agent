"""The pack reads only files inside the shared vault, holds back a page it cannot read from there, and a mount that
never answers costs the turn its snippets but not the rest of the process its threads.

[INPUT]
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults (POS: retrieves and budgets the snippets of the shared vaults within the timeout)
- myrm_agent_harness.observability.tracing::TracingContext (POS: ContextVar-based trace and session ids that log records are stamped with)
- myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::PUBLISH_STATUS_KEY (POS: wiki page frontmatter contract)
- tests.support.knowledge_pack_vaults::make_vault, titles, write_index (POS: shared vault fixtures of the knowledge-pack tests)

[OUTPUT]
- Tests that an index file, an indexed name and a page file that resolve outside the vault are never read, that such a
  page is held back and logged, that a page without any file, or whose link points at nothing, stands on its index row,
  that the scan runs in the context of the turn that asked, and that a scan which never returns leaves the default
  thread pool free and pins at most the four threads of the scan pool.

[POS]
Boundary and isolation counterpart of the retrieval cases in ``test_knowledge_pack.py``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path

import pytest
from myrm_agent_harness.observability.tracing import TracingContext
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import PUBLISH_STATUS_KEY

from app.services.wiki.knowledge_pack import selector
from app.services.wiki.knowledge_pack.selector import resolve_proactive_snippets_from_vaults
from tests.support.knowledge_pack_vaults import make_vault, titles, write_index

_QUERY = "zephyr budget limit"
_DRAFT = f"---\n{PUBLISH_STATUS_KEY}: draft\n---\nZephyr budget limit is a draft figure of 777.\n"
_PUBLISHED = "Zephyr budget limit is a published figure of 120.\n"
_needs_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks needs a privilege on Windows")


def _vault_with_a_page_linked_out(root: Path, target_text: str) -> Path:
    """An indexed vault whose only page file is a link to a file outside the vault holding `target_text`."""
    vault = make_vault(root, "kb", {}, indexed=False)
    outside = root / "outside"
    outside.mkdir()
    (outside / "Policy.md").write_text(target_text, encoding="utf-8")
    (vault / "wiki" / "concepts" / "Policy.md").symlink_to(outside / "Policy.md")
    write_index(vault, {"Policy": "Zephyr budget limit is an indexed figure."})
    return vault


@pytest.mark.asyncio
async def test_an_indexed_name_that_climbs_out_of_the_vault_is_held_back(tmp_path: Path) -> None:
    other = tmp_path / "other" / "wiki" / "concepts"
    other.mkdir(parents=True)
    (other / "payroll.md").write_text("Confidential zephyr budget limit payroll is 9 million.", encoding="utf-8")
    vault = make_vault(tmp_path, "kb", {}, indexed=False)
    write_index(vault, {"../../../other/wiki/concepts/payroll": "Zephyr budget limit filler words."})

    assert await titles(_QUERY, vault) == []


@pytest.mark.asyncio
@_needs_symlinks
@pytest.mark.parametrize("target_text", [_DRAFT, _PUBLISHED], ids=["draft", "published"])
async def test_an_indexed_page_linked_out_of_the_vault_is_held_back(tmp_path: Path, target_text: str) -> None:
    """Whatever the outside file says, its index row must not stand in for the page the publish gate cannot read."""
    assert await titles(_QUERY, _vault_with_a_page_linked_out(tmp_path, target_text)) == []


@pytest.mark.asyncio
async def test_an_indexed_page_without_any_file_stands_on_its_index_row(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "kb", {}, indexed=False)
    write_index(vault, {"Notes": "Zephyr budget limit is an indexed figure."})

    assert await titles(_QUERY, vault) == ["Notes"]


@pytest.mark.asyncio
@_needs_symlinks
async def test_an_indexed_page_whose_link_points_at_nothing_stands_on_its_index_row(tmp_path: Path) -> None:
    """A link to a missing target holds no file to read and no content to leak, so the page is a row of the index like
    any other without a file; treating the link itself as the page file would hold the page back instead."""
    vault = make_vault(tmp_path, "kb", {}, indexed=False)
    (vault / "wiki" / "concepts" / "Policy.md").symlink_to(tmp_path / "gone.md")
    write_index(vault, {"Policy": "Zephyr budget limit is an indexed figure."})

    assert await titles(_QUERY, vault) == ["Policy"]


@pytest.mark.asyncio
@_needs_symlinks
async def test_a_page_file_that_links_out_of_the_vault_is_not_scanned(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    secret = other / "payroll.md"
    secret.write_text("Confidential zephyr budget limit payroll is 9 million.", encoding="utf-8")
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    (vault / "wiki" / "concepts" / "leak.md").symlink_to(secret)

    assert await titles(_QUERY, vault) == ["Policy"]


@pytest.mark.asyncio
@_needs_symlinks
async def test_an_index_file_that_links_out_of_the_vault_is_not_read(tmp_path: Path) -> None:
    other = make_vault(tmp_path, "other", {}, indexed=False)
    write_index(other, {"Payroll": "Confidential zephyr budget limit payroll is 9 million."})
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    (vault / ".wiki_index.db").symlink_to(other / ".wiki_index.db")

    assert await titles(_QUERY, vault) == ["Policy"]


@pytest.mark.asyncio
@_needs_symlinks
async def test_a_refusal_is_logged_with_the_vault_and_the_escaped_path(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    vault = _vault_with_a_page_linked_out(tmp_path, _PUBLISHED)

    with caplog.at_level(logging.WARNING, logger=selector.__name__):
        await titles(_QUERY, vault)

    refusals = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(refusals) == 1
    assert str(vault) in refusals[0]
    assert repr(vault / "wiki" / "concepts" / "Policy.md") in refusals[0]


@pytest.mark.asyncio
async def test_the_scan_runs_in_the_context_of_the_turn_that_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """What the scan thread logs is stamped with the trace and session ids of the context it runs in."""
    seen: list[str] = []

    def probe(*_: object) -> list[object]:
        seen.append(TracingContext.get_session_id())
        return []

    monkeypatch.setattr(selector, "_scan_vault", probe)
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)

    token = TracingContext.set_session_id("turn-42")
    try:
        await titles(_QUERY, vault)
    finally:
        TracingContext.reset_session_id(token)

    assert seen == ["turn-42"]


@pytest.mark.asyncio
async def test_a_scan_that_never_returns_leaves_the_default_thread_pool_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mount that never answers pins one scan thread per turn, at most the four of the scan pool; the default pool,
    which every other `to_thread` caller in the process shares, must not be where they pile up."""
    release = threading.Event()

    def never_returns(*_: object) -> list[object]:
        release.wait(30)
        return []

    monkeypatch.setattr(selector, "_scan_vault", never_returns)
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    default_pool_size = min(32, (os.cpu_count() or 1) + 4)
    try:
        for _ in range(default_pool_size + 2):
            started = time.monotonic()
            result = await resolve_proactive_snippets_from_vaults(_QUERY, (vault,), {str(vault): "kb"}, timeout_seconds=0.05)
            assert result.snippets == []
            assert time.monotonic() - started < 0.5

        assert await asyncio.wait_for(asyncio.to_thread(lambda: "alive"), timeout=1.0) == "alive"
        assert sum(thread.name.startswith("knowledge-pack-scan") for thread in threading.enumerate()) == 4
    finally:
        release.set()
