"""Tests for the BM25 backend the agent injects into the wiki query engine.

The query engine calls the backend as ``(query, top_n)``; these tests call it the same way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.ai_agents.general_agent.wiki_search import build_wiki_bm25_search_fn

_GRAPH_NOTE = "Graph traversal visits every node of a graph. Breadth first search and depth first search are graph algorithms."
_COOKING_NOTE = "Sourdough bread needs a long fermentation. Hydration and flour choice change the crumb."


def _write_concept(vault: Path, name: str, text: str, *, raw: bytes | None = None) -> Path:
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    path = concepts / f"{name}.md"
    path.write_bytes(raw if raw is not None else text.encode("utf-8"))
    return path


async def test_ranks_the_matching_concept_first(tmp_path: Path) -> None:
    graph = _write_concept(tmp_path, "graphs", _GRAPH_NOTE)
    _write_concept(tmp_path, "bread", _COOKING_NOTE)

    results = await build_wiki_bm25_search_fn(tmp_path, [])("graph traversal algorithms", 5)

    assert [path for path, _ in results][:1] == [graph]
    assert all(score > 0 for _, score in results)


async def test_respects_top_n(tmp_path: Path) -> None:
    for index in range(4):
        _write_concept(tmp_path, f"graph-{index}", f"{_GRAPH_NOTE} variant {index}")

    results = await build_wiki_bm25_search_fn(tmp_path, [])("graph traversal", 2)

    assert len(results) == 2


async def test_includes_shared_read_only_vaults(tmp_path: Path) -> None:
    own, shared = tmp_path / "own", tmp_path / "shared"
    _write_concept(own, "bread", _COOKING_NOTE)
    shared_graph = _write_concept(shared, "graphs", _GRAPH_NOTE)

    results = await build_wiki_bm25_search_fn(own, [shared])("graph traversal", 5)

    assert [path for path, _ in results][:1] == [shared_graph]


async def test_skips_unreadable_concept_files(tmp_path: Path) -> None:
    graph = _write_concept(tmp_path, "graphs", _GRAPH_NOTE)
    _write_concept(tmp_path, "broken", "", raw=b"\xff\xfe\x00 not utf-8 \x80")

    results = await build_wiki_bm25_search_fn(tmp_path, [])("graph traversal", 5)

    assert [path for path, _ in results] == [graph]


async def test_empty_vault_yields_no_results(tmp_path: Path) -> None:
    assert await build_wiki_bm25_search_fn(tmp_path, [])("anything", 5) == []


async def test_agent_wires_its_vaults_into_the_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    own, shared = tmp_path / "own", tmp_path / "shared"
    graph = _write_concept(own, "graphs", _GRAPH_NOTE)
    _write_concept(shared, "bread", _COOKING_NOTE)
    monkeypatch.setattr(GeneralAgent, "_resolve_wiki_base_dir", lambda self: str(own))
    monkeypatch.setattr(GeneralAgent, "_resolve_wiki_public_dirs", lambda self: [str(shared)])

    search = object.__new__(GeneralAgent)._build_wiki_search_fn()
    results = await search("graph traversal", 5)

    assert [path for path, _ in results] == [graph]
