"""Directory grants in a worktree-isolated chat, and the refusal a drag-and-drop grant reports.

Sandbox mode promises that every file change stays in the temporary branch, so no folder outside the worktree
may be granted: not at turn start from a persisted grant, not by a drag-and-drop, not by an approval. A grant the
server refuses must say so instead of answering 200 with the unchanged list.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from myrm_agent_harness.agent.security.session_access import get_session_access_roots, set_session_access_roots

from app.services.agent.session_access_service import (
    DirectoryGrantRefusedError,
    access_roots_to_json,
    bootstrap_session_access_roots,
    grant_chat_session_access_root,
    is_directory_grant_allowed_for_deployment,
)


@pytest.fixture(autouse=True)
def _reset_session_roots() -> Iterator[None]:
    set_session_access_roots(())
    yield
    set_session_access_roots(())


class _FakeChat:
    def __init__(self, roots: list[dict[str, object]] | None = None) -> None:
        self.session_access_roots = roots or []


@pytest.fixture
def chat_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """One fake chat row; ``store['updates']`` holds what was last persisted."""
    store: dict[str, object] = {"chat": _FakeChat(), "updates": None}

    async def _get_chat(_chat_id: str) -> _FakeChat:
        chat = store["chat"]
        assert isinstance(chat, _FakeChat)
        return chat

    async def _update(_chat_id: str, updates: dict[str, object]) -> None:
        store["updates"] = updates
        chat = store["chat"]
        assert isinstance(chat, _FakeChat)
        chat.session_access_roots = list(updates["session_access_roots"])  # type: ignore[call-overload]

    monkeypatch.setattr("app.services.chat.chat_service.ChatService.get_chat_metadata", _get_chat)
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.update_chat_fields", _update)
    return store


@pytest.mark.parametrize("writable", [True, False])
def test_sandbox_mode_refuses_every_grant_read_only_ones_included(tmp_path, writable: bool) -> None:
    folder = tmp_path / "docs"
    folder.mkdir()

    assert (
        is_directory_grant_allowed_for_deployment(
            str(folder), workspace_dir=str(tmp_path / "ws"), sandbox_active=True, writable=writable
        )
        is False
    )
    assert (
        is_directory_grant_allowed_for_deployment(
            str(folder), workspace_dir=str(tmp_path / "ws"), sandbox_active=False, writable=writable
        )
        is True
    )


def test_a_persisted_grant_is_not_loaded_into_a_sandbox_turn(tmp_path) -> None:
    folder = tmp_path / "docs"
    folder.mkdir()
    persisted = [{"path": str(folder), "writable": False, "label": "", "source": "path_ask_grant"}]

    assert bootstrap_session_access_roots(persisted, workspace_dir=str(tmp_path), sandbox_active=True) == ()
    assert get_session_access_roots() == ()
    assert len(bootstrap_session_access_roots(persisted, workspace_dir=str(tmp_path), sandbox_active=False)) == 1


@pytest.mark.asyncio
async def test_a_drag_and_drop_grant_in_a_sandbox_chat_is_refused_and_persists_nothing(tmp_path, chat_store) -> None:
    folder = tmp_path / "dropped"
    folder.mkdir()

    with pytest.raises(DirectoryGrantRefusedError):
        await grant_chat_session_access_root("chat-1", str(folder), workspace_dir=str(tmp_path / "ws"), sandbox_active=True)

    assert chat_store["updates"] is None or chat_store["updates"] == {"session_access_roots": []}


@pytest.mark.asyncio
async def test_a_write_grant_over_a_home_directory_is_refused(tmp_path, chat_store) -> None:
    with pytest.raises(DirectoryGrantRefusedError):
        await grant_chat_session_access_root("chat-1", os.path.expanduser("~"), writable=True, workspace_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_granting_a_folder_again_is_not_a_refusal(tmp_path, chat_store) -> None:
    folder = tmp_path / "dropped"
    folder.mkdir()
    first = await grant_chat_session_access_root("chat-1", str(folder), writable=True, workspace_dir=str(tmp_path))

    again = await grant_chat_session_access_root("chat-1", str(folder), writable=False, workspace_dir=str(tmp_path))
    inside = await grant_chat_session_access_root("chat-1", str(folder / "sub"), writable=False, workspace_dir=str(tmp_path))

    assert access_roots_to_json(again) == access_roots_to_json(first)
    assert access_roots_to_json(inside) == access_roots_to_json(first)
