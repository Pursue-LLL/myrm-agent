"""Integration tests for session directory grant resume + persistence."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.session_access import (
    get_session_access_roots,
    merge_path_policy_with_session_access,
    set_session_access_roots,
)
from myrm_agent_harness.agent.security.types import AccessRoot, PathPolicy, PermissionAction

from app.services.agent.session_access_service import (
    access_roots_to_json,
    apply_directory_resume_grant,
    is_directory_grant_allowed_for_deployment,
    persist_chat_session_access_roots,
    revoke_chat_session_access_root,
)


@pytest.fixture(autouse=True)
def _reset_session_roots() -> None:
    set_session_access_roots(())


@pytest.mark.asyncio
async def test_directory_resume_grant_persists_and_allows_read(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    doc = downloads / "note.txt"
    doc.write_text("hello", encoding="utf-8")

    with patch(
        "app.services.agent.session_access_service.persist_chat_session_access_roots",
        new_callable=AsyncMock,
    ) as mock_persist:
        await apply_directory_resume_grant(
            "chat-session-access",
            {"granted": True, "path": str(downloads), "writable": False},
            workspace_dir=str(workspace),
        )
        mock_persist.assert_awaited_once_with("chat-session-access")

    roots = get_session_access_roots()
    assert len(roots) == 1
    assert roots[0].path == os.path.realpath(str(downloads))

    merged = merge_path_policy_with_session_access(PathPolicy())
    action, _ = check_path_policy(
        str(doc),
        merged,
        workspace_root=str(workspace),
        require_write=False,
    )
    assert action == PermissionAction.ALLOW


@pytest.mark.asyncio
async def test_path_ask_decision_grant_via_resume_payload(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()

    await apply_directory_resume_grant(
        None,
        {
            "decisions": [
                {
                    "type": "approve",
                    "extensions": {
                        "grantDirectory": True,
                        "grantDirectoryMeta": {
                            "path": str(extra),
                            "writable": False,
                        },
                    },
                }
            ]
        },
        workspace_dir=str(workspace),
    )

    roots = get_session_access_roots()
    assert len(roots) == 1
    assert roots[0].path == os.path.realpath(str(extra))


@pytest.mark.asyncio
async def test_directory_grant_blocked_in_sandbox_mode(tmp_path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    await apply_directory_resume_grant(
        "chat-sandbox",
        {"granted": True, "path": str(downloads), "writable": False},
        sandbox_active=True,
        workspace_dir=str(tmp_path / "ws"),
    )

    assert get_session_access_roots() == ()


def test_cloud_deployment_rejects_host_path_outside_volume(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "app.services.agent.session_access_service._is_cloud_volume_deployment",
        lambda: True,
    )

    host_path = str(tmp_path / "host-only")
    os.makedirs(host_path, exist_ok=True)
    assert is_directory_grant_allowed_for_deployment(
        host_path,
        workspace_dir=str(tmp_path / "ws"),
        sandbox_active=False,
    ) is False

    under_volume = "/persistent/workspace/project-a"
    assert is_directory_grant_allowed_for_deployment(
        under_volume,
        workspace_dir=None,
        sandbox_active=False,
    ) is True


@pytest.mark.asyncio
async def test_persist_session_access_roots_writes_chat_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """R2: persist path calls ChatService.update_chat_fields with session_access_roots JSON."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    captured: dict[str, object] = {}

    async def _fake_update(chat_id: str, updates: dict[str, object]) -> None:
        captured["chat_id"] = chat_id
        captured["updates"] = updates

    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        _fake_update,
    )

    await apply_directory_resume_grant(
        "chat-persist-r2",
        {"granted": True, "path": str(downloads), "writable": True},
        workspace_dir=str(workspace),
    )

    assert captured["chat_id"] == "chat-persist-r2"
    updates = captured["updates"]
    assert isinstance(updates, dict)
    roots_json = updates.get("session_access_roots")
    assert isinstance(roots_json, list)
    assert len(roots_json) == 1
    assert roots_json[0]["path"] == os.path.realpath(str(downloads))
    assert roots_json[0]["writable"] is True
    assert roots_json[0]["source"] == "hitl_grant"


@pytest.mark.asyncio
async def test_persist_session_access_roots_direct_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()

    from myrm_agent_harness.agent.security.session_access import grant_session_access_root
    from myrm_agent_harness.agent.security.types import AccessRoot

    grant_session_access_root(
        AccessRoot(path=str(extra), writable=False, source="path_ask_grant"),
        workspace_root=str(workspace),
    )

    captured: dict[str, object] = {}

    async def _fake_update(chat_id: str, updates: dict[str, object]) -> None:
        captured["chat_id"] = chat_id
        captured["updates"] = updates

    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        _fake_update,
    )

    await persist_chat_session_access_roots("chat-direct")

    assert captured["chat_id"] == "chat-direct"
    updates = captured["updates"]
    assert isinstance(updates, dict)
    expected = access_roots_to_json(get_session_access_roots())
    assert updates["session_access_roots"] == expected
    assert len(expected) == 1
    assert expected[0]["path"] == os.path.realpath(str(extra))


@pytest.mark.asyncio
async def test_directory_resume_grant_skips_persist_when_grant_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        update_mock,
    )

    await apply_directory_resume_grant(
        "chat-no-grant",
        {"granted": True, "path": "/etc/passwd", "writable": False},
        workspace_dir=str(tmp_path / "ws"),
    )

    update_mock.assert_not_called()
    assert get_session_access_roots() == ()


@pytest.mark.asyncio
async def test_revoke_chat_session_access_root_persists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()

    roots_json = access_roots_to_json(
        (
            AccessRoot(path=str(downloads), writable=False, source="hitl_grant"),
            AccessRoot(path=str(extra), writable=True, source="path_ask_grant"),
        )
    )

    class _FakeChat:
        session_access_roots = roots_json

    async def _fake_get_chat(_chat_id: str) -> _FakeChat:
        return _FakeChat()

    captured: dict[str, object] = {}

    async def _fake_update(chat_id: str, updates: dict[str, object]) -> None:
        captured["chat_id"] = chat_id
        captured["updates"] = updates

    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        _fake_get_chat,
    )
    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        _fake_update,
    )

    updated = await revoke_chat_session_access_root(
        "chat-revoke",
        str(downloads),
        workspace_dir=str(workspace),
    )

    assert len(updated) == 1
    assert updated[0].path == os.path.realpath(str(extra))
    assert captured["chat_id"] == "chat-revoke"
    updates = captured["updates"]
    assert isinstance(updates, dict)
    persisted = updates.get("session_access_roots")
    assert isinstance(persisted, list)
    assert len(persisted) == 1
    assert persisted[0]["path"] == os.path.realpath(str(extra))


@pytest.mark.asyncio
async def test_orchestrator_resume_grant_path_persists_via_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Resume grant path used by orchestrator persists through ChatService.update_chat_fields."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = tmp_path / "external"
    target.mkdir()

    captured: dict[str, object] = {}

    async def _fake_update(chat_id: str, updates: dict[str, object]) -> None:
        captured["chat_id"] = chat_id
        captured["updates"] = updates

    monkeypatch.setattr(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        _fake_update,
    )

    await apply_directory_resume_grant(
        "chat-orchestrator-resume",
        {"granted": True, "path": str(target), "writable": False},
        workspace_dir=str(workspace),
    )

    assert captured["chat_id"] == "chat-orchestrator-resume"
    roots_json = captured["updates"]["session_access_roots"]
    assert isinstance(roots_json, list)
    assert roots_json[0]["path"] == os.path.realpath(str(target))
    assert get_session_access_roots()[0].path == os.path.realpath(str(target))
