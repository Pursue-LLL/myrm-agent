"""Wiki portability export and agent scope API tests."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Annotated
from unittest.mock import MagicMock

from fastapi import Query
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure


def _override_archiver_app(mock_archiver: MagicMock):
    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    return app


def test_wiki_portability_export_zip_contains_manifest_and_concepts(tmp_path: Path) -> None:
    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()

    concept_path = structure.get_concept_file_path("ExportConcept")
    concept_path.write_text("---\ntype: concept\n---\nExport body\n", encoding="utf-8")
    structure.get_index_file_path().write_text("# Index\n", encoding="utf-8")
    structure.get_log_file_path().write_text("# Log\n", encoding="utf-8")

    mock_archiver = MagicMock()
    mock_archiver._structure = structure

    app = _override_archiver_app(mock_archiver)
    client = TestClient(app)
    try:
        response = client.get("/api/v1/wiki/portability/export")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert any(name.startswith("wiki/concepts/") for name in names)
        assert "wiki/index.md" in names
        assert "wiki/log.md" in names

        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["version"] == 2
        assert manifest["concepts_count"] >= 1


def test_wiki_pending_edits_respects_agent_scope_query(tmp_path: Path) -> None:
    from app.services.wiki.vault import reset_wiki_archiver_cache_for_tests

    structure_a = WikiStructure(tmp_path / "vault-a")
    structure_b = WikiStructure(tmp_path / "vault-b")
    structure_a.ensure_structure()
    structure_b.ensure_structure()

    mock_archiver_a = MagicMock()
    mock_archiver_a._structure = structure_a
    mock_archiver_a._pending_mgr.get_pending_edits.return_value = [
        {
            "id": 1,
            "concept_name": "AgentAConcept",
            "proposed_content": "A draft",
            "status": "pending",
            "created_at": "2026-07-29T00:00:00+00:00",
            "updated_at": "2026-07-29T00:00:00+00:00",
        }
    ]
    mock_archiver_a._pending_mgr.get_stats.return_value = {"pending": 1}

    mock_archiver_b = MagicMock()
    mock_archiver_b._structure = structure_b
    mock_archiver_b._pending_mgr.get_pending_edits.return_value = []
    mock_archiver_b._pending_mgr.get_stats.return_value = {"pending": 0}

    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    reset_wiki_archiver_cache_for_tests()

    async def _scoped_archiver(
        agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    ) -> MagicMock:
        if agent_id == "agent-b":
            return mock_archiver_b
        return mock_archiver_a

    app.dependency_overrides[_get_wiki_archiver] = _scoped_archiver
    client = TestClient(app)
    try:
        scoped_response = client.get("/api/v1/wiki/pending?agent_id=agent-a")
        other_response = client.get("/api/v1/wiki/pending?agent_id=agent-b")
    finally:
        app.dependency_overrides.clear()
        reset_wiki_archiver_cache_for_tests()

    assert scoped_response.status_code == 200
    assert scoped_response.json()["pending_edits"][0]["concept_name"] == "AgentAConcept"
    assert other_response.status_code == 200
    assert other_response.json()["pending_edits"] == []
