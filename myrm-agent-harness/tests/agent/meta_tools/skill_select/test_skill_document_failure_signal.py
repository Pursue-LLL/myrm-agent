"""A skill whose SOP cannot be read is not delivered, not counted as loaded and not recorded as used.

The tool-level tests stub ``get_skill_document``. These tests run the real loader and the real tool over a
backend whose read fails, so the contract between the backend, the loader and the tool is what is under test.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.agent.meta_tools.skills.select.skill_document_loader import get_skill_document
from myrm_agent_harness.agent.meta_tools.skills.select.skill_select_tool import create_select_skill_tool
from myrm_agent_harness.agent.skill_agent.context import get_loaded_skills, reset_loaded_skills
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.backends.skills.usage_recorder import begin_skill_run_usage, commit_skill_run_usage

_LOADER_LOGGER = "myrm_agent_harness.agent.meta_tools.skills.select.skill_document_loader"
_SOP = "# demo\n\nStep 1: run it.\n"


def _stored_skill(tmp_path: Path) -> SkillMetadata:
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    return SkillMetadata(name="demo", description="demo skill", storage_skill_id="demo", storage_path=str(skill_dir))


async def test_a_failed_read_yields_no_document_and_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    backend = AsyncMock()
    backend.get_skill_content.side_effect = OSError("storage unavailable")

    with caplog.at_level(logging.WARNING, logger=_LOADER_LOGGER):
        document = await get_skill_document(_stored_skill(tmp_path), backend)

    assert document == ""
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert "demo" in record.getMessage()
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], OSError)


async def test_an_unreadable_skill_is_neither_loaded_nor_used_and_a_retry_delivers_it(tmp_path: Path) -> None:
    skill = _stored_skill(tmp_path)
    ledger = tmp_path / "demo" / ".stats.json"
    backend = AsyncMock()
    backend.get_skill_content.side_effect = [OSError("storage unavailable"), _SOP]
    tool = create_select_skill_tool([skill], backend)
    reset_loaded_skills()

    begin_skill_run_usage()
    failed = await tool.ainvoke({"skill_names": ["demo"], "reason": "first try"})
    commit_skill_run_usage()

    assert 'status="error"' in failed
    assert get_loaded_skills() == []
    assert not ledger.exists()

    begin_skill_run_usage()
    retried = await tool.ainvoke({"skill_names": ["demo"], "reason": "retry"})
    commit_skill_run_usage()

    assert 'status="ready"' in retried
    assert "Step 1: run it." in retried
    assert [loaded.name for loaded in get_loaded_skills()] == ["demo"]
    assert SkillStatsCollector().get_stats(tmp_path / "demo").call_count == 1
