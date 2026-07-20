"""Integration tests for google-workspace skill bash invocation pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.agent.meta_tools.bash.bash_executor import BashExecutor
from myrm_agent_harness.agent.skills.runtime.env import detect_skill_script_command
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.toolkits.storage.paths import get_skill_file_path
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills import prebuilt_sync

GOOGLE_CALENDAR_CMD = (
    "python3 .claude/skills/google-workspace/scripts/google_api.py calendar-today"
)


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture(autouse=True)
def reset_sync_flag() -> None:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.mark.asyncio
async def test_google_workspace_script_synced_to_storage(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    script_path = get_skill_file_path(
        SkillType.PREBUILT, "google-workspace", "scripts/google_api.py"
    )
    content = await storage.read_text(script_path)
    assert "calendar-today" in content


def test_google_workspace_command_detects_hyphenated_skill_name() -> None:
    detected, skill_name = detect_skill_script_command(GOOGLE_CALENDAR_CMD)
    assert detected is True
    assert skill_name == "google-workspace"


def test_bash_executor_detects_google_workspace_skill_command() -> None:
    mock_executor = MagicMock()
    mock_executor.config = MagicMock()
    executor = BashExecutor(executor=mock_executor, enable_skill_execution=False)
    assert executor._detect_skill_from_code(GOOGLE_CALENDAR_CMD) == "google-workspace"  # noqa: SLF001
