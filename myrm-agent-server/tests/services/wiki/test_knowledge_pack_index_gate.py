"""The knowledge pack reads published pages from a real wiki index, whatever drafts and sidecar rows surround them.

[INPUT]
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults
- myrm_agent_harness.toolkits.wiki.retrieval.indexer::WikiIndexer (POS: builds the index the way the harness writes it)
- myrm_agent_harness.toolkits.wiki.pipeline.publication::publish_concept_article (POS: the write + index path every published page goes through)

[OUTPUT]
- Tests that drafts and blocked pages in the index never crowd published pages out of the pack, that sidecar index rows
  never reach it, that a page whose file cannot be read is held back whole, that so is a page whose file was removed
  after it was indexed (logged once per scan), that rows the pack holds back give way to the published pages behind them
  up to the row window, that an interim raw entry, which has no page file, still stands on its index row, and that
  pages published under names with ``.md`` or a vault prefix reach the pack from the rows the pipeline wrote.

[POS]
Real-index counterpart of the hand-built vaults in ``test_knowledge_pack.py``.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.publication import ArticlePublishOutcome, publish_concept_article
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

from app.services.wiki.knowledge_pack import selector
from app.services.wiki.knowledge_pack.schemas import ProactiveKnowledgeResult
from app.services.wiki.knowledge_pack.selector import resolve_proactive_snippets_from_vaults

_QUERY = "zephyr budget limit"
_CROWDING = "Zephyr budget limit " * 10

_PUBLISHED = {
    "Hotel Limits": "Zephyr budget limit: hotel stays in Berlin are capped at 120 per night.",
    "Flight Rules": "Zephyr budget limit for conference travel allows economy flights only, booked two weeks ahead.",
    "Meal Allowance": "Zephyr budget limit on meals covers 45 daily, receipts required within thirty days.",
}


def _page(status: str | None, text: str) -> str:
    status_line = f"publish_status: {status}\n" if status else ""
    return f"---\ntype: concept\n{status_line}---\n## Compiled Truth\n{text}\n"


class _Vault:
    """A vault built the way the harness builds one: page files plus their rows in the real index."""

    def __init__(self, root: Path) -> None:
        self.structure = WikiStructure(root / "vault")
        self.structure.ensure_structure()
        self.indexer = WikiIndexer(self.structure, WikiConfig(enable_hybrid_search=False))

    @property
    def path(self) -> Path:
        return self.structure.base_dir

    async def add_page(self, name: str, status: str | None, text: str) -> None:
        page = _page(status, text)
        (self.structure.concepts_dir / f"{name}.md").write_text(page, encoding="utf-8")
        await self.indexer.upsert(name, page)

    async def publish(self, name: str, text: str) -> None:
        """Publish through the pipeline: the file path and the index key come from the harness, not from the test."""
        outcome = await publish_concept_article(self.structure, self.indexer, name, _page(None, text))
        assert outcome is ArticlePublishOutcome.PUBLISHED

    async def pack(self) -> ProactiveKnowledgeResult:
        return await resolve_proactive_snippets_from_vaults(_QUERY, (self.path,), {str(self.path): "kb"}, timeout_seconds=2.0)


@pytest.fixture
def vault(tmp_path: Path) -> _Vault:
    return _Vault(tmp_path)


async def test_drafts_and_blocked_pages_do_not_starve_the_pack(vault: _Vault) -> None:
    # More pages than the markdown scan reads, so only the index can find the published ones.
    for i in range(40):
        await vault.add_page(f"Filler {i}", None, f"Gardening note {i} about tomatoes and compost.")
    for i in range(6):
        await vault.add_page(f"Draft {i}", "draft", f"{_CROWDING}{900 + i} awaiting approval")
    for i in range(3):
        await vault.add_page(f"Blocked {i}", "blocked", f"{_CROWDING}{700 + i} stopped by the gate")
    for name, text in _PUBLISHED.items():
        await vault.add_page(name, None, text)

    result = await vault.pack()

    assert sorted(s.article_title for s in result.snippets) == sorted(_PUBLISHED)
    assert all("Draft" not in s.snippet and "Blocked" not in s.snippet for s in result.snippets)
    assert not any(str(n) in s.snippet for s in result.snippets for n in (*range(900, 906), *range(700, 703)))


async def test_sidecar_index_rows_never_reach_the_pack(vault: _Vault) -> None:
    await vault.add_page("Hotel Limits", None, _PUBLISHED["Hotel Limits"])
    conn = sqlite3.connect(vault.indexer.db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content, search_terms) VALUES (?, ?, ?)",
                ("__sidecar__:L0:policies", f"{_CROWDING}directory summary", _CROWDING),
            )
    finally:
        conn.close()

    result = await vault.pack()

    assert [s.article_title for s in result.snippets] == ["Hotel Limits"]


async def test_a_page_whose_file_cannot_be_read_is_held_back_whole(vault: _Vault, monkeypatch: pytest.MonkeyPatch) -> None:
    await vault.add_page("Hotel Limits", None, _PUBLISHED["Hotel Limits"])
    await vault.add_page("Locked Page", None, "Zephyr budget limit text only the index still holds.")
    read_text = Path.read_text

    def unreadable_locked_page(self: Path, encoding: str | None = None, errors: str | None = None) -> str:
        if self.name == "Locked Page.md":
            raise PermissionError(self.name)
        return read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", unreadable_locked_page)

    result = await vault.pack()

    assert [s.article_title for s in result.snippets] == ["Hotel Limits"]


async def test_a_page_removed_after_it_was_indexed_is_held_back_and_logged(
    vault: _Vault, caplog: pytest.LogCaptureFixture
) -> None:
    await vault.add_page("Hotel Limits", None, _PUBLISHED["Hotel Limits"])
    await vault.add_page("Old Policy", None, "Zephyr budget limit used to be 300 per night, a retired figure.")
    (vault.structure.concepts_dir / "Old Policy.md").unlink()

    with caplog.at_level(logging.WARNING, logger=selector.__name__):
        result = await vault.pack()

    assert [s.article_title for s in result.snippets] == ["Hotel Limits"]
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert repr("Old Policy") in warnings[0]


async def test_an_interim_raw_entry_stands_on_its_index_row(vault: _Vault) -> None:
    """A raw upload waiting to be compiled has an index row and never a page file."""
    await vault.add_page("Hotel Limits", None, _PUBLISHED["Hotel Limits"])
    vault.indexer.index_raw_text("upload", "Zephyr budget limit quokka notes waiting to be compiled.")

    result = await vault.pack()

    assert sorted(s.article_title for s in result.snippets) == ["Hotel Limits", "raw:upload"]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]


@pytest.mark.parametrize("name", ["AGENTS.md", "AI Agents/SKILL.md", "docs/Intro.md", "wiki/concepts/Guide"])
async def test_a_page_published_under_a_file_like_name_reaches_the_pack(
    vault: _Vault, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    await vault.publish(name, _PUBLISHED["Hotel Limits"])

    with caplog.at_level(logging.WARNING, logger=selector.__name__):
        result = await vault.pack()

    assert [s.snippet for s in result.snippets] == [_PUBLISHED["Hotel Limits"]]
    assert _warnings(caplog) == []


async def test_republishing_a_page_by_its_file_name_adds_no_row_the_pack_holds_back(
    vault: _Vault, caplog: pytest.LogCaptureFixture
) -> None:
    await vault.publish("AGENTS.md", _PUBLISHED["Hotel Limits"])
    page = next(iter(vault.structure.list_concepts()))
    await vault.publish(page.relative_to(vault.structure.concepts_dir).with_suffix("").as_posix(), _PUBLISHED["Hotel Limits"])

    with caplog.at_level(logging.WARNING, logger=selector.__name__):
        result = await vault.pack()

    assert len(result.snippets) == 1
    assert _warnings(caplog) == []


async def test_a_page_and_one_named_with_md_suffix_are_both_found(vault: _Vault) -> None:
    await vault.publish("Notes", "Zephyr budget limit for alpha pilots: hotel stays are capped at 90 per night.")
    await vault.publish("Notes.md", "Zephyr budget limit for bravo crews: rental cars are capped at 40 per day.")

    result = await vault.pack()

    found = {s.article_title: s.snippet for s in result.snippets}
    assert sorted(found) == ["notes", "notesmd"]
    assert "alpha" in found["notes"]
    assert "bravo" in found["notesmd"]


@pytest.mark.parametrize(("past_the_window", "found"), [(0, len(_PUBLISHED)), (1, len(_PUBLISHED) - 1)])
async def test_stale_rows_give_way_to_the_published_pages_behind_them(
    vault: _Vault, caplog: pytest.LogCaptureFixture, past_the_window: int, found: int
) -> None:
    for name, text in _PUBLISHED.items():
        await vault.publish(name, text)
    stale = [f"Retired {i}" for i in range(selector._MAX_INDEXED_ROWS - len(_PUBLISHED) + past_the_window)]
    for i, name in enumerate(stale):
        await vault.publish(name, f"{_CROWDING}{900 + i}")
        vault.structure.get_concept_file_path(name).unlink()

    with caplog.at_level(logging.WARNING, logger=selector.__name__):
        result = await vault.pack()

    assert len(result.snippets) == found
    assert all(s.article_title.replace("-", " ") in {n.lower() for n in _PUBLISHED} for s in result.snippets)
    (warning,) = _warnings(caplog)
    assert str(len(stale)) in warning
    assert sum(name.lower().replace(" ", "-") in warning for name in stale) <= 3


async def test_a_draft_the_index_still_lists_as_published_gives_way_to_the_published_pages_behind_it(
    vault: _Vault, caplog: pytest.LogCaptureFixture
) -> None:
    for name, text in _PUBLISHED.items():
        await vault.publish(name, text)
    for i in range(6):
        await vault.publish(f"Pending {i}", f"{_CROWDING}{900 + i}")
        vault.structure.get_concept_file_path(f"Pending {i}").write_text(
            _page("draft", f"{_CROWDING}{900 + i}"), encoding="utf-8"
        )

    with caplog.at_level(logging.WARNING, logger=selector.__name__):
        result = await vault.pack()

    assert len(result.snippets) == len(_PUBLISHED)
    assert _warnings(caplog) == []
