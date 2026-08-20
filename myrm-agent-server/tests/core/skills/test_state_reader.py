"""Unit tests for SQLiteSkillStateReader connection strategy.

Covers the process-shared store reuse (default), the explicit db_path
independent-store path, and the exception fallback behavior.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord

from app.core.skills.state_reader import SQLiteSkillStateReader
from app.core.skills.store.evolution_store import reset_evolution_skill_store


def test_default_path_reuses_shared_store(monkeypatch) -> None:
    """Without db_path, is_skill_active must go through the shared singleton."""
    reset_evolution_skill_store()
    store = MagicMock()
    record = MagicMock(spec=SkillRecord)
    record.is_active = False
    store.get_skill.return_value = record

    with patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        return_value=store,
    ) as mock_get:
        reader = SQLiteSkillStateReader()
        active = reader.is_skill_active("blocked-skill")

    assert active is False
    store.get_skill.assert_called_once_with("blocked-skill")
    mock_get.assert_called_once()
    store.close.assert_not_called()
    reset_evolution_skill_store()


def test_injected_db_path_uses_independent_store(monkeypatch) -> None:
    """With db_path, an independent SkillStore is created and closed per call."""
    db_path = Path("/tmp/nonexistent-skills.db")
    independent = MagicMock()
    record = MagicMock(spec=SkillRecord)
    record.is_active = True
    independent.get_skill.return_value = record

    with patch("app.core.skills.state_reader.SkillStore", return_value=independent) as mock_cls:
        reader = SQLiteSkillStateReader(db_path=db_path)
        active = reader.is_skill_active("normal-skill")

    assert active is True
    mock_cls.assert_called_once_with(db_path=db_path)
    independent.get_skill.assert_called_once_with("normal-skill")
    independent.close.assert_called_once()


def test_missing_record_defaults_to_active(monkeypatch) -> None:
    """Unknown skills are treated as active (quarantine only hides known ones)."""
    reset_evolution_skill_store()
    store = MagicMock()
    store.get_skill.return_value = None

    with patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        return_value=store,
    ):
        reader = SQLiteSkillStateReader()
        assert reader.is_skill_active("unknown-skill") is True
    reset_evolution_skill_store()


def test_exception_falls_back_to_active(monkeypatch) -> None:
    """DB errors must not block skill loading (fallback to active)."""
    reset_evolution_skill_store()
    store = MagicMock()
    store.get_skill.side_effect = RuntimeError("db locked")

    with patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        return_value=store,
    ):
        reader = SQLiteSkillStateReader()
        assert reader.is_skill_active("skill") is True
    reset_evolution_skill_store()


def test_store_resolution_exception_falls_back_to_active(monkeypatch) -> None:
    """Connection-resolution failure must also fall back to active."""
    reset_evolution_skill_store()
    with patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        side_effect=RuntimeError("connection init failed"),
    ):
        reader = SQLiteSkillStateReader()
        assert reader.is_skill_active("skill") is True
    reset_evolution_skill_store()
