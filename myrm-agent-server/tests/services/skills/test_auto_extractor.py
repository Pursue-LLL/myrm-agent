"""Test auto_extractor.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.skills.auto_extractor import (
    auto_extract_or_patch_skill,
    publish_skill_evolved_event,
)


@pytest.fixture
def mock_skill_creation_service():
    with patch("app.services.skills.auto_extractor.skill_creation_service") as mock_service:
        # Mock save_skill to return a success result
        mock_result = MagicMock()
        mock_result.success = True
        mock_service.save_skill = AsyncMock(return_value=mock_result)

        # Mock base_path and path exists
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "Original content"
        mock_dir = MagicMock()
        mock_dir.__truediv__.return_value = mock_path
        mock_service.base_path.__truediv__.return_value = mock_dir

        yield mock_service


@pytest.fixture
def mock_publish_event():
    with patch("app.services.skills.auto_extractor.publish_skill_evolved_event") as mock_pub:
        yield mock_pub


@pytest.fixture
def mock_apply_patch():
    with patch("app.services.skills.auto_extractor.apply_skill_patch") as mock_patch:
        mock_patch_result = MagicMock()
        mock_patch_result.success = True
        mock_patch_result.content = "Patched content"
        mock_patch.return_value = mock_patch_result
        yield mock_patch


@pytest.mark.asyncio
async def test_auto_extract_new_skill(mock_skill_creation_service, mock_publish_event):
    result = {
        "user_id": "test_user_1",
        "has_value": True,
        "type": "skill_draft",
        "skill_name": "test_skill",
        "skill_description": "A new skill",
        "trigger_condition": "When asked",
        "skill_steps": "Do this",
    }

    await auto_extract_or_patch_skill(result)

    mock_skill_creation_service.save_skill.assert_called_once()
    kwargs = mock_skill_creation_service.save_skill.call_args.kwargs
    assert kwargs["name"] == "test_skill"
    assert kwargs["description"] == "A new skill"
    assert "Trigger Condition" in kwargs["content"]
    assert "When asked" in kwargs["content"]

    mock_publish_event.assert_called_once_with(
        skill_name="test_skill",
        evolution_type="new",
        description="A new skill",
    )


@pytest.mark.asyncio
async def test_auto_patch_existing_skill(mock_skill_creation_service, mock_publish_event, mock_apply_patch):
    result = {
        "user_id": "test_user_2",
        "has_value": True,
        "type": "skill_patch",
        "skill_name": "existing_skill",
        "patch_content": "Replace something",
    }

    await auto_extract_or_patch_skill(result)

    mock_apply_patch.assert_called_once()

    mock_skill_creation_service.save_skill.assert_called_once()
    kwargs = mock_skill_creation_service.save_skill.call_args.kwargs
    assert kwargs["name"] == "existing_skill"
    assert kwargs["content"] == "Patched content"

    mock_publish_event.assert_called_once_with(
        skill_name="existing_skill",
        evolution_type="patch",
        description="Applied optimization patch",
    )


@pytest.mark.asyncio
@patch("app.services.skills.evolution_events.get_event_bus")
async def test_publish_evolution_event(mock_get_bus):
    mock_bus = MagicMock()
    mock_get_bus.return_value = mock_bus

    publish_skill_evolved_event(skill_name="my_skill", evolution_type="new", description="desc")

    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args.args[0]
    assert event.event_type == "skill_evolved"  # AppEventType.SKILL_EVOLVED
    assert event.data["skill_name"] == "my_skill"
    assert event.data["evolution_type"] == "new"


@pytest.mark.asyncio
async def test_auto_extract_persists_eval_cases(mock_skill_creation_service, mock_publish_event):
    """Review eval_cases must be written into the evolution SkillStore for new skills."""
    eval_cases = [
        {
            "message": "deploy nginx",
            "sandbox_assertions": [{"type": "code_contains", "target": "nginx"}],
        }
    ]
    result = {
        "user_id": "test_user_3",
        "has_value": True,
        "type": "skill_draft",
        "skill_name": "test_skill_eval",
        "skill_description": "A new skill with eval cases",
        "trigger_condition": "When asked",
        "skill_steps": "Deploy the service",
        "eval_cases": eval_cases,
    }

    mock_store = MagicMock()
    mock_store.get_skill_by_name_version.return_value = None
    mock_store.save_skill = AsyncMock()
    mock_store.close = MagicMock()

    with patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        return_value=mock_store,
    ):
        materialization = await auto_extract_or_patch_skill(result, eval_cases=eval_cases)

    assert materialization.success
    mock_store.save_skill.assert_awaited_once()
    saved_record = mock_store.save_skill.call_args.args[0]
    assert saved_record.name == "test_skill_eval"
    assert saved_record.eval_cases == eval_cases
