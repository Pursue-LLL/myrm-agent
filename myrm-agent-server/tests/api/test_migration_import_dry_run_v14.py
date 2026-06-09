"""API integration tests for competitor import dry-run (v1.4 routing)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="migrations_api")
pytestmark = pytest.mark.xdist_group(name="migration_import_api")


@pytest.fixture()
def client() -> TestClient:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app)


@pytest.fixture()
def openclaw_fixture(tmp_path: Path) -> Path:
    root = tmp_path / ".openclaw"
    root.mkdir()
    (root / "sessions.json").write_text(
        json.dumps(
            [
                {
                    "title": "Release",
                    "summary": "Shipped migration fix",
                    "created_at": "2024-06-01T00:00:00Z",
                },
            ],
        ),
        encoding="utf-8",
    )
    (root / "memory.json").write_text(
        json.dumps([{"content": "User prefers concise answers"}]),
        encoding="utf-8",
    )
    workspace = root / "workspace-main"
    workspace.mkdir()
    (workspace / "SOUL.md").write_text("Be concise.", encoding="utf-8")
    (workspace / "MEMORY.md").write_text("- Workspace bullet fact", encoding="utf-8")
    return root


@pytest.fixture()
def hermes_fixture(tmp_path: Path) -> Path:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / "SOUL.md").write_text("Be precise.", encoding="utf-8")
    memories = root / "memories"
    memories.mkdir()
    (memories / "MEMORY.md").write_text("- Prefers concise answers", encoding="utf-8")
    return root


@pytest.fixture()
def claude_fixture(tmp_path: Path) -> Path:
    root = tmp_path / ".claude"
    root.mkdir()
    (root / "CLAUDE.md").write_text("Always run tests before merge.", encoding="utf-8")
    (root / "settings.json").write_text('{"model": "claude-sonnet"}', encoding="utf-8")
    skills = root / "skills" / "review"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nname: review\n---\nReview code", encoding="utf-8")
    return root


class TestCompetitorImportDryRunApi:
    @pytest.fixture(autouse=True)
    def _local_mode(self) -> None:
        with (
            patch("app.api.migration.discovery.is_local_mode", return_value=True),
            patch("app.services.migration.competitor_payload_loader.is_local_mode", return_value=True),
        ):
            yield  # type: ignore[misc]

    def test_openclaw_dry_run_maps_sessions_and_memory(
        self,
        client: TestClient,
        openclaw_fixture: Path,
    ) -> None:
        payload = {
            "source": "auto",
            "payload": {
                "competitor": "openclaw",
                "root": str(openclaw_fixture),
                "files": [],
            },
            "migration": {
                "include_episodic": True,
                "apply_global_instructions": True,
            },
        }
        resp = client.post("/api/v1/memory/import/dry-run", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["summary"]["source"] == "openclaw"
        assert body["result"]["summary"]["mapped_items"] >= 2
        lanes = {lane["lane"]: lane for lane in body["migration_lanes"]}
        assert "memory" in lanes
        assert "episodic" not in lanes["memory"]["detail"] or "mapped" in lanes["memory"]["detail"]
        mapping_buckets = {m["source_bucket"] for m in body["result"]["mappings"]}
        assert "openclaw_sessions" in mapping_buckets

    def test_hermes_dry_run_splits_instruction_and_memory(
        self,
        client: TestClient,
        hermes_fixture: Path,
    ) -> None:
        payload = {
            "source": "auto",
            "payload": {
                "competitor": "hermes",
                "root": str(hermes_fixture),
                "files": [],
            },
            "migration": {"apply_global_instructions": True},
        }
        resp = client.post("/api/v1/memory/import/dry-run", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["summary"]["source"] == "hermes"
        assert body["result"]["summary"]["mapped_items"] >= 1
        assert body.get("instruction_total_chars", 0) > 0
        coverage_labels = {item["label"] for item in body.get("coverage_items", [])}
        assert "mcp_manual" in coverage_labels
        assert "channels_manual" in coverage_labels
        assert "unsupported_source" not in body["result"]["warnings"]

    def test_claude_dry_run_stages_skills(
        self,
        client: TestClient,
        claude_fixture: Path,
    ) -> None:
        payload = {
            "source": "claude",
            "payload": {
                "competitor": "claude",
                "root": str(claude_fixture),
                "files": [],
            },
            "migration": {"apply_global_instructions": True},
        }
        resp = client.post("/api/v1/memory/import/dry-run", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["summary"]["status"] == "ready"
        assert body["result"]["summary"]["source"] == "claude"
        assert len(body["pending_skills"]) == 1
        assert body["pending_skills"][0]["name"] == "review"
        assert "unsupported_source" not in body["result"]["warnings"]

    def test_cursor_dry_run_instruction_rules_only(self, client: TestClient, tmp_path: Path) -> None:
        root = tmp_path / ".cursor"
        root.mkdir()
        rules = root / "rules"
        rules.mkdir()
        (rules / "style.md").write_text("Use TypeScript strict mode.", encoding="utf-8")

        payload = {
            "source": "auto",
            "payload": {"competitor": "cursor", "root": str(root), "files": []},
            "migration": {"apply_global_instructions": True},
        }
        resp = client.post("/api/v1/memory/import/dry-run", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["instruction_preview_rule_names"]) >= 1
        assert body["result"]["summary"]["status"] == "ready"
        assert body["result"]["summary"]["mapped_items"] == 0
        assert "unsupported_source" not in body["result"]["warnings"]

    def test_codex_dry_run_instruction_lane(self, client: TestClient, tmp_path: Path) -> None:
        root = tmp_path / ".codex"
        root.mkdir()
        (root / "instructions.md").write_text("Prefer small diffs.", encoding="utf-8")
        (root / "config.json").write_text('{"model": "gpt-4o"}', encoding="utf-8")

        payload = {
            "source": "auto",
            "payload": {"competitor": "codex", "root": str(root), "files": []},
            "migration": {"apply_global_instructions": True},
        }
        resp = client.post("/api/v1/memory/import/dry-run", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "small diffs" in (body.get("instruction_preview_persona") or "").lower() or (
            body.get("instruction_total_chars", 0) > 0
        )
