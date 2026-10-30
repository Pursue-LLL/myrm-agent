"""The knowledge pack reads published pages from a real wiki index, whatever drafts and sidecar rows surround them.

[INPUT]
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults
- myrm_agent_harness.toolkits.wiki.retrieval.indexer::WikiIndexer (POS: builds the index the way the harness writes it)

[OUTPUT]
- Tests that drafts and blocked pages in the index never crowd published pages out of the pack, that sidecar index rows
  never reach it, and that a page whose file cannot be read is held back whole.

[POS]
Real-index counterpart of the hand-built vaults in ``test_knowledge_pack.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

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
