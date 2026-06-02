from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.backends.skills import QuarantineAwareSkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata


@pytest.fixture
def mock_base_backend():
    backend = MagicMock()
    backend.list_skills = AsyncMock()
    backend.load_skills = AsyncMock()
    backend.get_skill_content = AsyncMock()
    backend.get_skill_resources = AsyncMock()
    backend.list_skill_resources = AsyncMock()
    return backend


@pytest.fixture
def mock_state_reader():
    reader = MagicMock()
    reader.is_skill_active = MagicMock(return_value=True)
    return reader


@pytest.fixture
def quarantine_backend(mock_base_backend, mock_state_reader):
    return QuarantineAwareSkillBackend(base_backend=mock_base_backend, state_reader=mock_state_reader)


@pytest.mark.asyncio
async def test_list_skills_filters_inactive(quarantine_backend, mock_base_backend, mock_state_reader):
    skill1 = SkillMetadata(name="skill1", description="s1")
    skill2 = SkillMetadata(name="skill2", description="s2")
    skill3 = SkillMetadata(name="skill3", description="s3")
    mock_base_backend.list_skills.return_value = [skill1, skill2, skill3]

    def is_active(name):
        return name != "skill2"

    mock_state_reader.is_skill_active.side_effect = is_active

    filtered_skills = await quarantine_backend.list_skills()

    assert len(filtered_skills) == 2
    assert filtered_skills[0].name == "skill1"
    assert filtered_skills[1].name == "skill3"


@pytest.mark.asyncio
async def test_load_skills_filters_inactive(quarantine_backend, mock_base_backend, mock_state_reader):
    skill1 = SkillMetadata(name="skill1", description="s1")
    mock_base_backend.load_skills.return_value = [skill1]
    mock_state_reader.is_skill_active.return_value = False

    filtered_skills = await quarantine_backend.load_skills(["skill1"])

    assert len(filtered_skills) == 0


@pytest.mark.asyncio
async def test_filter_active_handles_exception(quarantine_backend, mock_base_backend, mock_state_reader):
    skill1 = SkillMetadata(name="skill1", description="s1")
    mock_base_backend.list_skills.return_value = [skill1]
    mock_state_reader.is_skill_active.side_effect = Exception("DB Error")

    filtered_skills = await quarantine_backend.list_skills()

    # Should fallback to returning all skills
    assert len(filtered_skills) == 1
    assert filtered_skills[0].name == "skill1"


@pytest.mark.asyncio
async def test_delegates_other_methods(quarantine_backend, mock_base_backend, mock_state_reader):
    mock_state_reader.is_skill_active.return_value = True

    mock_base_backend.get_skill_content.return_value = "content"
    assert await quarantine_backend.get_skill_content("skill1") == "content"
    mock_base_backend.get_skill_content.assert_called_once_with("skill1")

    mock_base_backend.get_skill_resources.return_value = b"bytes"
    assert await quarantine_backend.get_skill_resources("skill1", "path") == b"bytes"
    mock_base_backend.get_skill_resources.assert_called_once_with("skill1", "path")

    mock_base_backend.list_skill_resources.return_value = ["file1"]
    assert await quarantine_backend.list_skill_resources("skill1") == ["file1"]
    mock_base_backend.list_skill_resources.assert_called_once_with("skill1")


@pytest.mark.asyncio
async def test_blocks_inactive_skill_content(quarantine_backend, mock_base_backend, mock_state_reader):
    mock_state_reader.is_skill_active.return_value = False

    with pytest.raises(FileNotFoundError, match="is quarantined"):
        await quarantine_backend.get_skill_content("skill1")

    with pytest.raises(FileNotFoundError, match="is quarantined"):
        await quarantine_backend.get_skill_resources("skill1", "path")

    assert await quarantine_backend.list_skill_resources("skill1") == []
