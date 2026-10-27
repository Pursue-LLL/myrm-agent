"""``resolve_effective_chat_workspace`` never hands the sandbox a stored folder the bind gate would refuse."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.database.dto import ChatDTO
from app.services.chat.effective_workspace import resolve_effective_chat_workspace

HOME = str(Path.home())
_GET_PROJECT_TARGET = "app.services.project.project_service.ProjectService.get_project"


def _chat(workspace_dir: str | None = None, project_id: str | None = None) -> ChatDTO:
    now = datetime.now(UTC)
    return ChatDTO(id="c1", workspace_dir=workspace_dir, project_id=project_id, created_at=now, updated_at=now)


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "state"
    folder.mkdir()
    monkeypatch.setattr(
        "app.config.settings.get_settings",
        lambda: SimpleNamespace(database=SimpleNamespace(state_dir=str(folder))),
    )
    return folder


async def test_an_ordinary_stored_folder_is_used(tmp_path: Path) -> None:
    assert await resolve_effective_chat_workspace(_chat(str(tmp_path)), jit_fallback=False) == str(tmp_path)


@pytest.mark.parametrize("stored", [HOME, "/"])
async def test_a_stored_folder_containing_protected_locations_is_skipped(stored: str) -> None:
    assert await resolve_effective_chat_workspace(_chat(stored), jit_fallback=False) is None


async def test_a_stored_state_directory_is_skipped(state_dir: Path) -> None:
    assert await resolve_effective_chat_workspace(_chat(str(state_dir)), jit_fallback=False) is None
    assert await resolve_effective_chat_workspace(_chat(str(state_dir.parent)), jit_fallback=False) is None


async def test_an_unusable_project_folder_yields_to_the_chat_folder(state_dir: Path, tmp_path: Path) -> None:
    chat_folder = tmp_path / "chat-folder"
    chat_folder.mkdir()
    project = SimpleNamespace(workspace_path=str(state_dir))

    with patch(_GET_PROJECT_TARGET, AsyncMock(return_value=project)):
        resolved = await resolve_effective_chat_workspace(_chat(str(chat_folder), project_id="p1"), jit_fallback=False)

    assert resolved == str(chat_folder)
