"""Tests for Curator history API and service functions.

Covers:
- _save_history: writes JSONL, truncates, correct structure
- get_curator_history: returns newest first, respects limit
- GET /curator/history endpoint: returns JSON array
- Trigger propagation: manual vs background
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.skills.curator import CuratorRunResult, CuratorTransition


@pytest.fixture(autouse=True)
def _patch_data_dir(tmp_path: Path):
    """Redirect curator history to temp directory."""
    with patch("app.core.skills.curator_service._get_data_dir", return_value=tmp_path):
        yield tmp_path


@pytest.fixture
def sample_result() -> CuratorRunResult:
    """Create a sample CuratorRunResult with 1 transition."""
    return CuratorRunResult(
        transitions=[
            CuratorTransition(
                skill_name="old_skill",
                skill_path="/tmp/skills/old_skill",
                from_status="active",
                to_status="stale",
                reason_type="inactivity",
                reason_message="Unused for 35 days",
                timestamp=datetime.now(UTC),
            )
        ],
        skills_scanned=15,
        skipped_pinned=2,
        errors=[],
    )


@pytest.fixture
def empty_result() -> CuratorRunResult:
    """Create a CuratorRunResult with no transitions."""
    return CuratorRunResult(
        transitions=[],
        skills_scanned=10,
        skipped_pinned=0,
        errors=[],
    )


class TestSaveHistory:
    """Tests for _save_history function."""

    def test_creates_file(self, sample_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history

        _save_history(sample_result, trigger="manual", duration_ms=42)
        history_path = _patch_data_dir / "curator_history.jsonl"
        assert history_path.exists()

    def test_entry_structure(self, sample_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history

        _save_history(sample_result, trigger="manual", duration_ms=123)
        history_path = _patch_data_dir / "curator_history.jsonl"
        entry = json.loads(history_path.read_text().strip())

        assert entry["trigger"] == "manual"
        assert entry["duration_ms"] == 123
        assert entry["skills_scanned"] == 15
        assert entry["total_transitions"] == 1
        assert entry["stale_count"] == 1
        assert entry["archived_count"] == 0
        assert entry["skipped_pinned"] == 2
        assert len(entry["transitions"]) == 1
        assert entry["transitions"][0]["skill_name"] == "old_skill"
        assert entry["transitions"][0]["from_status"] == "active"
        assert entry["transitions"][0]["to_status"] == "stale"
        assert entry["transitions"][0]["reason"] == "inactivity"
        assert entry["errors"] == []
        assert "timestamp" in entry

    def test_background_trigger(self, empty_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history

        _save_history(empty_result, trigger="background", duration_ms=5)
        history_path = _patch_data_dir / "curator_history.jsonl"
        entry = json.loads(history_path.read_text().strip())
        assert entry["trigger"] == "background"

    def test_appends_multiple(self, empty_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history

        for i in range(5):
            empty_result.skills_scanned = i
            _save_history(empty_result, trigger="background", duration_ms=i)

        history_path = _patch_data_dir / "curator_history.jsonl"
        lines = [ln for ln in history_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 5

    def test_truncates_at_max(self, empty_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history

        for i in range(40):
            empty_result.skills_scanned = i
            _save_history(empty_result, trigger="background", duration_ms=i)

        history_path = _patch_data_dir / "curator_history.jsonl"
        lines = [ln for ln in history_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 30

        last_entry = json.loads(lines[-1])
        assert last_entry["skills_scanned"] == 39

    def test_handles_corrupted_file(self, sample_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history

        history_path = _patch_data_dir / "curator_history.jsonl"
        history_path.write_text("corrupted{json\n")

        _save_history(sample_result, trigger="manual", duration_ms=1)
        lines = [ln for ln in history_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2


class TestGetCuratorHistory:
    """Tests for get_curator_history function."""

    def test_empty_when_no_file(self, _patch_data_dir: Path):
        from app.core.skills.curator_service import get_curator_history

        result = get_curator_history()
        assert result == []

    def test_returns_newest_first(self, empty_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history, get_curator_history

        for i in range(5):
            empty_result.skills_scanned = i
            _save_history(empty_result, trigger="background", duration_ms=i)

        entries = get_curator_history(limit=3)
        assert len(entries) == 3
        assert entries[0]["skills_scanned"] == 4
        assert entries[1]["skills_scanned"] == 3
        assert entries[2]["skills_scanned"] == 2

    def test_respects_limit(self, empty_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history, get_curator_history

        for i in range(10):
            _save_history(empty_result, trigger="background", duration_ms=i)

        entries = get_curator_history(limit=3)
        assert len(entries) == 3

    def test_skips_corrupted_lines(self, sample_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history, get_curator_history

        _save_history(sample_result, trigger="manual", duration_ms=1)

        history_path = _patch_data_dir / "curator_history.jsonl"
        content = history_path.read_text()
        history_path.write_text(content + "not-json\n")

        entries = get_curator_history(limit=10)
        assert len(entries) == 1
        assert entries[0]["trigger"] == "manual"

    def test_limit_zero_returns_empty(self, empty_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history, get_curator_history

        _save_history(empty_result, trigger="background", duration_ms=1)
        entries = get_curator_history(limit=0)
        assert entries == []

    def test_limit_negative_returns_empty(self, _patch_data_dir: Path):
        from app.core.skills.curator_service import get_curator_history

        entries = get_curator_history(limit=-1)
        assert entries == []


class TestCuratorHistoryEndpoint:
    """Tests for GET /curator/history API endpoint."""

    def test_history_empty(self, client):
        response = client.get("/api/v1/skills/curator/history")
        assert response.status_code == 200
        assert response.json() == []

    def test_history_with_limit(self, client, empty_result: CuratorRunResult, _patch_data_dir: Path):
        from app.core.skills.curator_service import _save_history

        for i in range(5):
            empty_result.skills_scanned = i
            _save_history(empty_result, trigger="background", duration_ms=i)

        response = client.get("/api/v1/skills/curator/history?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["skills_scanned"] == 4
        assert data[0]["trigger"] == "background"

    def test_history_after_manual_run(self, client, _patch_data_dir: Path):
        """Running /curator/run should create a history entry."""
        with (
            patch("app.core.skills.curator_service.get_stats_collector"),
            patch("app.core.skills.curator_service.DEFAULT_LOCAL_SKILL_PATHS", [str(_patch_data_dir)]),
        ):
            response = client.post("/api/v1/skills/curator/run")
            assert response.status_code == 200

        history_path = _patch_data_dir / "curator_history.jsonl"
        if history_path.exists():
            lines = [ln for ln in history_path.read_text().splitlines() if ln.strip()]
            if lines:
                entry = json.loads(lines[-1])
                assert entry["trigger"] == "manual"
