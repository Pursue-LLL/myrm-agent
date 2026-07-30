"""Tests for Obsidian vault export presets."""

from __future__ import annotations

import json
import zipfile

import pytest

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.obsidian_export import build_obsidian_graph_json, build_obsidian_vault_zip


@pytest.fixture
def temp_vault(tmp_path) -> WikiStructure:
    structure = WikiStructure(tmp_path / "agent-vault")
    structure.ensure_structure()
    concept_path = structure.get_concept_file_path("Comparisons/demo/Evolution")
    concept_path.write_text("---\ntype: comparison\n---\n\n# Evolution\n", encoding="utf-8")
    return structure


def test_build_obsidian_graph_json_has_type_color_groups() -> None:
    graph = build_obsidian_graph_json()
    queries = [entry["query"] for entry in graph["colorGroups"]]
    assert "[type:comparison]" in queries
    assert "[type:concept]" in queries
    assert "path:Comparisons/" not in queries
    assert len(graph["colorGroups"]) == 7
    assert isinstance(graph["search"], str)


def test_build_obsidian_vault_zip_includes_graph_and_readme(temp_vault: WikiStructure) -> None:
    archive = build_obsidian_vault_zip(temp_vault, agent_id="default")
    with zipfile.ZipFile(archive) as zf:
        assert ".obsidian/graph.json" in zf.namelist()
        assert "README-OBSIDIAN.txt" in zf.namelist()
        graph = json.loads(zf.read(".obsidian/graph.json"))
        assert graph["hideUnresolved"] is True
