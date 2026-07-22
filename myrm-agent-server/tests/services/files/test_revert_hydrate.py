"""Unit tests for app.services.files.revert_hydrate."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    FileSnapshot,
    SnapshotOp,
    SnapshotStore,
)
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver


@pytest.fixture(autouse=True)
def _reset_snapshot_store() -> None:
    SnapshotStore.reset()
    yield
    SnapshotStore.reset()


class TestResolveSnapshotSearchRoots:
    @pytest.mark.asyncio
    async def test_includes_workspace_env_and_deduplicates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.files.revert_hydrate import _resolve_snapshot_search_roots

        root = tmp_path.resolve()
        monkeypatch.setenv("WORKSPACE_ROOT", str(root))
        WorkspacePathResolver._cached_workspace_root = root

        session_id = f"chat_{uuid.uuid4().hex[:8]}"
        fake_chat = MagicMock()
        fake_chat.workspace_dir = str(root)

        with patch(
            "app.services.chat.chat_service.ChatService.get_chat_by_id",
            new_callable=AsyncMock,
            return_value=fake_chat,
        ), patch(
            "app.services.agent.params.workspace_resolve.resolve_default_chat_workspace_dir",
            new_callable=AsyncMock,
            return_value=str(root),
        ):
            roots = await _resolve_snapshot_search_roots(session_id)

        assert roots == [root]

    @pytest.mark.asyncio
    async def test_includes_distinct_chat_and_harness_roots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.files.revert_hydrate import _resolve_snapshot_search_roots

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        harness_root = (tmp_path / "harness_root").resolve()
        chat_root = (tmp_path / "chat_root").resolve()
        chat_root.mkdir()
        harness_root.mkdir()
        WorkspacePathResolver._cached_workspace_root = harness_root

        session_id = f"chat_{uuid.uuid4().hex[:8]}"
        fake_chat = MagicMock()
        fake_chat.workspace_dir = str(chat_root)

        with patch(
            "app.services.chat.chat_service.ChatService.get_chat_by_id",
            new_callable=AsyncMock,
            return_value=fake_chat,
        ), patch(
            "app.services.agent.params.workspace_resolve.resolve_default_chat_workspace_dir",
            new_callable=AsyncMock,
            return_value=None,
        ):
            roots = await _resolve_snapshot_search_roots(session_id)

        assert roots == [harness_root, chat_root]

    @pytest.mark.asyncio
    async def test_swallows_chat_lookup_errors(self, tmp_path: Path) -> None:
        from app.services.files.revert_hydrate import _resolve_snapshot_search_roots

        harness_root = tmp_path.resolve()
        WorkspacePathResolver._cached_workspace_root = harness_root

        with patch(
            "app.services.chat.chat_service.ChatService.get_chat_by_id",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db down"),
        ), patch(
            "app.services.agent.params.workspace_resolve.resolve_default_chat_workspace_dir",
            new_callable=AsyncMock,
            return_value=None,
        ):
            roots = await _resolve_snapshot_search_roots("chat_x")

        assert roots == [harness_root]

    @pytest.mark.asyncio
    async def test_swallows_harness_root_resolution_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.files.revert_hydrate import _resolve_snapshot_search_roots

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)

        with patch(
            "myrm_agent_harness.toolkits.code_execution.utils.workspace_path.WorkspacePathResolver.resolve_workspace_root",
            side_effect=RuntimeError("no root"),
        ), patch(
            "app.services.chat.chat_service.ChatService.get_chat_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.services.agent.params.workspace_resolve.resolve_default_chat_workspace_dir",
            new_callable=AsyncMock,
            return_value=None,
        ):
            roots = await _resolve_snapshot_search_roots("chat_x")

        assert roots == []

    @pytest.mark.asyncio
    async def test_swallows_default_workspace_resolution_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.files.revert_hydrate import _resolve_snapshot_search_roots

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        harness_root = tmp_path.resolve()
        WorkspacePathResolver._cached_workspace_root = harness_root

        with patch(
            "app.services.chat.chat_service.ChatService.get_chat_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.services.agent.params.workspace_resolve.resolve_default_chat_workspace_dir",
            new_callable=AsyncMock,
            side_effect=RuntimeError("workspace svc down"),
        ):
            roots = await _resolve_snapshot_search_roots("chat_x")

        assert roots == [harness_root]


class TestEnsureSessionSnapshotsHydrated:
    @pytest.mark.asyncio
    async def test_skips_when_memory_already_has_snapshots(self) -> None:
        from app.services.files.revert_hydrate import ensure_session_snapshots_hydrated

        store = SnapshotStore.get()
        store.record(
            "chat_1",
            "msg_1",
            FileSnapshot(path="/tmp/a.txt", operation=SnapshotOp.MODIFY, original_content="x"),
        )

        with patch(
            "app.services.files.revert_hydrate._resolve_snapshot_search_roots",
            new_callable=AsyncMock,
        ) as mock_roots:
            await ensure_session_snapshots_hydrated("chat_1")

        mock_roots.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_loads_first_matching_root_from_disk(self, tmp_path: Path) -> None:
        from app.services.files.revert_hydrate import ensure_session_snapshots_hydrated

        persist_root = tmp_path.resolve()
        session_id = "chat_hydrate"
        message_id = "msg_hydrate"
        file_path = persist_root / "notes.txt"
        file_path.write_text("after\n", encoding="utf-8")

        disk_store = SnapshotStore.get()
        disk_store.record(
            session_id,
            message_id,
            FileSnapshot(
                path=str(file_path),
                operation=SnapshotOp.MODIFY,
                original_content="before\n",
            ),
        )
        await disk_store.persist_to_disk(str(persist_root), session_id, message_id)
        SnapshotStore.reset()

        with patch(
            "app.services.files.revert_hydrate._resolve_snapshot_search_roots",
            new_callable=AsyncMock,
            return_value=[persist_root],
        ):
            await ensure_session_snapshots_hydrated(session_id)

        loaded = SnapshotStore.get().get_message_snapshots(session_id, message_id)
        assert len(loaded) == 1
        assert loaded[0].original_content == "before\n"


class TestCleanupPersistedSnapshots:
    @pytest.mark.asyncio
    async def test_cleanup_message_deletes_json(self, tmp_path: Path) -> None:
        from app.services.files.revert_hydrate import cleanup_persisted_snapshots

        persist_root = tmp_path.resolve()
        session_id = "chat_cleanup"
        message_id = "msg_cleanup"

        store = SnapshotStore.get()
        store.record(
            session_id,
            message_id,
            FileSnapshot(
                path=str(persist_root / "a.txt"),
                operation=SnapshotOp.CREATE,
                original_content=None,
            ),
        )
        await store.persist_to_disk(str(persist_root), session_id, message_id)
        target = persist_root / ".myrm" / "snapshots" / session_id / f"{message_id}.json"
        assert target.is_file()

        with patch(
            "app.services.files.revert_hydrate._resolve_snapshot_search_roots",
            new_callable=AsyncMock,
            return_value=[persist_root],
        ):
            await cleanup_persisted_snapshots(session_id, message_id)

        assert not target.is_file()

    @pytest.mark.asyncio
    async def test_cleanup_session_deletes_directory(self, tmp_path: Path) -> None:
        from app.services.files.revert_hydrate import cleanup_persisted_snapshots

        persist_root = tmp_path.resolve()
        session_id = "chat_session_cleanup"
        message_id = "msg_session_cleanup"

        store = SnapshotStore.get()
        store.record(
            session_id,
            message_id,
            FileSnapshot(
                path=str(persist_root / "b.txt"),
                operation=SnapshotOp.CREATE,
                original_content=None,
            ),
        )
        await store.persist_to_disk(str(persist_root), session_id, message_id)
        session_dir = persist_root / ".myrm" / "snapshots" / session_id
        assert session_dir.is_dir()

        with patch(
            "app.services.files.revert_hydrate._resolve_snapshot_search_roots",
            new_callable=AsyncMock,
            return_value=[persist_root],
        ):
            await cleanup_persisted_snapshots(session_id)

        assert not session_dir.exists()
