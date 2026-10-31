"""Vault builders of the knowledge-pack tests: page files, with or without a matching FTS index.

[INPUT]
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig (POS: the budget and dedup limits of one injection)
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults (POS: retrieves and budgets the snippets of the shared vaults within the timeout)
- myrm_agent_harness.toolkits.retriever.cjk_tokenizer::build_cjk_index_segment (POS: writes the CJK search column the way the index does)
- myrm_agent_harness.utils.markdown_frontmatter::parse_frontmatter (POS: BOM-tolerant frontmatter parse SSOT)

[OUTPUT]
- make_vault: A vault holding the given page files; with `indexed`, every page also gets a row in the FTS index.
- write_index: An index file whose rows another process wrote: the names are not checked against the vault's files.
- titles: The article titles the pack injects for a question over the given vaults.

[POS]
Shared fixtures of the knowledge-pack test files, so the index schema is spelled out in one place.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from myrm_agent_harness.toolkits.retriever.cjk_tokenizer import build_cjk_index_segment
from myrm_agent_harness.utils.markdown_frontmatter import parse_frontmatter

from app.services.wiki.knowledge_pack.schemas import KnowledgePackConfig
from app.services.wiki.knowledge_pack.selector import resolve_proactive_snippets_from_vaults

_CREATE_FTS = 'CREATE VIRTUAL TABLE wiki_fts USING fts5(concept_name, truth_content, tokenize="unicode61 remove_diacritics 1")'


def write_index(vault: Path, rows: dict[str, str]) -> None:
    """Create the vault's FTS index with exactly these (concept name, indexed text) rows."""
    with sqlite3.connect(vault / ".wiki_index.db") as conn:
        conn.execute(_CREATE_FTS)
        conn.executemany("INSERT INTO wiki_fts(concept_name, truth_content) VALUES (?, ?)", list(rows.items()))


def make_vault(root: Path, name: str, pages: dict[str, str], *, indexed: bool) -> Path:
    """A vault holding the given page files; with `indexed`, every page also gets a row in the FTS index."""
    vault = root / name
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    for page_name, page in pages.items():
        (concepts / f"{page_name}.md").write_text(page, encoding="utf-8")
    if indexed:
        write_index(vault, {page_name: build_cjk_index_segment(parse_frontmatter(page)[1]) for page_name, page in pages.items()})
    return vault


async def titles(query: str, *vaults: Path, config: KnowledgePackConfig | None = None) -> list[str]:
    """The article titles the pack injects for `query`, each vault labelled with its directory name."""
    result = await resolve_proactive_snippets_from_vaults(
        query,
        vaults,
        {str(v): v.name for v in vaults},
        config=config,
        timeout_seconds=2.0,
    )
    return [snippet.article_title for snippet in result.snippets]
