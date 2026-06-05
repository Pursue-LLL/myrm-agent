"""Integration tests for GET /api/v1/workspace/rules.

Tests use real filesystem to verify workspace rule discovery
and API response format end-to-end. Uses monkeypatch to point
get_workspace_root to temp directories with real rule files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def workspace_with_rules(tmp_path: Path) -> Path:
    """Create a workspace directory with various rule files."""
    (tmp_path / "AGENTS.md").write_text("# Project Rules\nUse Python 3.13")
    (tmp_path / ".cursorrules").write_text("Always use type hints")

    myrm_rules = tmp_path / ".myrm" / "rules"
    myrm_rules.mkdir(parents=True)
    (myrm_rules / "coding.md").write_text("# Coding Standards\nFollow PEP8")

    cursor_rules = tmp_path / ".cursor" / "rules"
    cursor_rules.mkdir(parents=True)
    (cursor_rules / "style.mdc").write_text("---\nmodel: gpt-4\n---\nUse consistent naming")

    return tmp_path


@pytest.fixture
def empty_workspace(tmp_path: Path) -> Path:
    """Create an empty workspace directory."""
    return tmp_path


class TestWorkspaceRulesEndpoint:
    """Tests for GET /api/v1/workspace/rules."""

    def test_returns_discovered_rules(
        self, client: TestClient, workspace_with_rules: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.api.dependencies.get_workspace_root",
            lambda: workspace_with_rules,
        )
        response = client.get("/api/v1/workspace/rules")
        assert response.status_code == 200

        data = response.json()
        assert "rules" in data
        assert "total_chars" in data
        assert "workspace_root" in data
        assert data["workspace_root"] == str(workspace_with_rules)
        assert len(data["rules"]) >= 3
        assert data["total_chars"] > 0

        sources = [r["source"] for r in data["rules"]]
        assert "AGENTS.md" in sources
        assert ".cursorrules" in sources

    def test_rule_item_schema(self, client: TestClient, workspace_with_rules: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.api.dependencies.get_workspace_root",
            lambda: workspace_with_rules,
        )
        response = client.get("/api/v1/workspace/rules")
        data = response.json()

        for rule in data["rules"]:
            assert "path" in rule
            assert "source" in rule
            assert "char_count" in rule
            assert "truncated" in rule
            assert isinstance(rule["char_count"], int)
            assert isinstance(rule["truncated"], bool)
            assert rule["char_count"] > 0

    def test_empty_workspace_returns_empty_list(
        self, client: TestClient, empty_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.api.dependencies.get_workspace_root",
            lambda: empty_workspace,
        )
        response = client.get("/api/v1/workspace/rules")
        assert response.status_code == 200

        data = response.json()
        assert data["rules"] == []
        assert data["total_chars"] == 0

    def test_frontmatter_stripped_from_mdc(
        self, client: TestClient, workspace_with_rules: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.api.dependencies.get_workspace_root",
            lambda: workspace_with_rules,
        )
        response = client.get("/api/v1/workspace/rules")
        data = response.json()

        mdc_rules = [r for r in data["rules"] if ".cursor/rules" in r["source"]]
        assert len(mdc_rules) >= 1
        for rule in mdc_rules:
            assert rule["char_count"] < 50

    def test_truncation_flag_for_large_file(self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        large_content = "x" * 9000
        (tmp_path / "AGENTS.md").write_text(large_content)

        monkeypatch.setattr(
            "app.api.dependencies.get_workspace_root",
            lambda: tmp_path,
        )
        response = client.get("/api/v1/workspace/rules")
        data = response.json()

        assert len(data["rules"]) == 1
        rule = data["rules"][0]
        assert rule["truncated"] is True
        assert rule["char_count"] < 9000
