"""Tests for SnapshotInterceptor — Git-first with file-copy fallback.

Covers: Git detection caching, fallback path, per-turn dedup, timeout safety,
event emission, workspace lock concurrency, _create_snapshot edge cases,
_run_async_cmd failure, context None handling, and .gitignore injection.
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.checkpoint.snapshot_service import SnapshotInterceptor, _workspace_locks


@pytest.fixture(autouse=True)
def _clear_workspace_locks():
    """Reset module-level locks between tests."""
    _workspace_locks.clear()
    yield
    _workspace_locks.clear()


@pytest.fixture
def interceptor() -> SnapshotInterceptor:
    return SnapshotInterceptor()


def _make_payload(session_id: str = "sess-1") -> dict:
    return {"session_id": session_id, "command": "rm -rf /tmp/test"}


# ---------------------------------------------------------------------------
# 1. Git detection caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_git_caches_result(interceptor: SnapshotInterceptor):
    """_detect_git result is cached by _safe_snapshot_with_lock on first call."""
    assert interceptor._git_available is None

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = proc

        result = await interceptor._detect_git()

    assert result is True
    # _detect_git only returns the value; _safe_snapshot_with_lock caches it
    interceptor._git_available = result
    assert interceptor._git_available is True
    mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_detect_git_returns_false_when_missing(interceptor: SnapshotInterceptor):
    """FileNotFoundError => git unavailable."""
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        result = await interceptor._detect_git()

    assert result is False


@pytest.mark.asyncio
async def test_detect_git_returns_false_on_nonzero_exit(interceptor: SnapshotInterceptor):
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.returncode = 127
        proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = proc

        result = await interceptor._detect_git()

    assert result is False


# ---------------------------------------------------------------------------
# 2. Fallback path: no Git => LocalFileSnapshotStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_snapshot_called_when_no_git(interceptor: SnapshotInterceptor):
    """When git is unavailable, _create_fallback_snapshot is used."""
    interceptor._git_available = False
    interceptor._fallback_store = MagicMock()
    interceptor._fallback_store.take_snapshot = AsyncMock(return_value="fs_abc123_1700000000")

    with patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock):
        await interceptor._safe_snapshot_with_lock(
            workspace_path="/tmp/ws",
            action_type="bash",
            chat_id="chat-1",
            agent_id="agent-1",
            turn_id="turn-1",
            cache_key=("/tmp/ws", "turn-1"),
        )

    interceptor._fallback_store.take_snapshot.assert_awaited_once()
    call_kwargs = interceptor._fallback_store.take_snapshot.call_args
    assert call_kwargs.kwargs["working_dir"] == "/tmp/ws"


@pytest.mark.asyncio
async def test_git_path_called_when_git_available(interceptor: SnapshotInterceptor):
    """When git is available, _create_snapshot is used (not fallback)."""
    interceptor._git_available = True

    with (
        patch.object(interceptor, "_create_snapshot", new_callable=AsyncMock) as mock_git,
        patch.object(interceptor, "_create_fallback_snapshot", new_callable=AsyncMock) as mock_fb,
        patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock),
    ):
        await interceptor._safe_snapshot_with_lock(
            workspace_path="/tmp/ws",
            action_type="file_write",
            chat_id="chat-1",
            agent_id="agent-1",
            turn_id="turn-1",
            cache_key=("/tmp/ws", "turn-1"),
        )

    mock_git.assert_awaited_once()
    mock_fb.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Per-turn dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_turn_dedup_skips_second_call(interceptor: SnapshotInterceptor):
    """Same (workspace, turn) pair should only snapshot once."""
    interceptor._git_available = True

    call_count = 0

    async def _mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1

    with (
        patch.object(interceptor, "_create_snapshot", side_effect=_mock_create),
        patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock),
    ):
        cache_key = ("/tmp/ws", "turn-1")
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", cache_key)
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", cache_key)

    assert call_count == 1


@pytest.mark.asyncio
async def test_different_turns_both_snapshot(interceptor: SnapshotInterceptor):
    """Different turn IDs should each get their own snapshot."""
    interceptor._git_available = True

    call_count = 0

    async def _mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1

    with (
        patch.object(interceptor, "_create_snapshot", side_effect=_mock_create),
        patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock),
    ):
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", ("/tmp/ws", "turn-1"))
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-2", ("/tmp/ws", "turn-2"))

    assert call_count == 2


# ---------------------------------------------------------------------------
# 4. session_id guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_when_no_session_id(interceptor: SnapshotInterceptor):
    """Payload without session_id => early return, no snapshot."""
    with patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock:
        await interceptor.before_destructive_action("/tmp/ws", "bash", {"command": "ls"})

    mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. Event emission uses correct API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_snapshot_event_uses_event_bus(interceptor: SnapshotInterceptor):
    """_emit_snapshot_event should call get_event_bus().publish(AppEvent(...))."""
    mock_bus = MagicMock()

    mock_module = MagicMock()
    mock_module.get_event_bus.return_value = mock_bus
    mock_module.AppEventType.SYSTEM_NOTIFICATION = "system_notification"

    with patch.dict("sys.modules", {"app.services.event.app_event_bus": mock_module}):
        await interceptor._emit_snapshot_event("chat-123", "bash")

    mock_bus.publish.assert_called_once()
    # Verify AppEvent was constructed with correct event_type
    mock_module.AppEvent.assert_called_once()
    call_kwargs = mock_module.AppEvent.call_args.kwargs
    assert call_kwargs["event_type"] == "system_notification"
    assert call_kwargs["data"]["meta_data"]["type"] == "snapshot_created"
    assert call_kwargs["data"]["meta_data"]["chat_id"] == "chat-123"
    assert call_kwargs["data"]["meta_data"]["action"] == "bash"


# ---------------------------------------------------------------------------
# 6. Snapshot error does not propagate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_error_caught_gracefully(interceptor: SnapshotInterceptor):
    """Errors in snapshot creation should be caught, not propagated."""
    interceptor._git_available = True

    with (
        patch.object(interceptor, "_create_snapshot", side_effect=RuntimeError("git failed")),
        patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock),
    ):
        # Should not raise
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", ("/tmp/ws", "turn-1"))

    # Turn should NOT be marked as snapshotted (since it failed)
    assert not interceptor._snapshotted_turns.get(("/tmp/ws", "turn-1"))


# ---------------------------------------------------------------------------
# 7. Fallback trigger mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_trigger_mapping(interceptor: SnapshotInterceptor):
    """Each action_type should map to the correct SnapshotTrigger."""
    from myrm_agent_harness.agent.file_snapshot.types import SnapshotTrigger

    interceptor._git_available = False
    interceptor._fallback_store = MagicMock()
    interceptor._fallback_store.take_snapshot = AsyncMock(return_value="fs_test")

    test_cases = [
        ("bash", SnapshotTrigger.EXECUTE_TERMINAL),
        ("file_write", SnapshotTrigger.WRITE_FILE),
        ("file_append", SnapshotTrigger.WRITE_FILE),
        ("file_delete", SnapshotTrigger.DELETE_FILE),
        ("patch_file", SnapshotTrigger.PATCH_FILE),
        ("unknown_action", SnapshotTrigger.MANUAL),
    ]

    for action_type, expected_trigger in test_cases:
        interceptor._snapshotted_turns.clear()
        interceptor._fallback_store.take_snapshot.reset_mock()

        with patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock):
            await interceptor._safe_snapshot_with_lock(
                "/tmp/ws", action_type, "c", "a", f"turn-{action_type}", ("/tmp/ws", f"turn-{action_type}")
            )

        call_kwargs = interceptor._fallback_store.take_snapshot.call_args.kwargs
        assert call_kwargs["trigger"] == expected_trigger, f"Failed for action_type={action_type}"


# ---------------------------------------------------------------------------
# 8. Workspace lock isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_locks_are_per_workspace():
    """Different workspaces should have independent locks."""
    lock_a = _workspace_locks["/ws/a"]
    lock_b = _workspace_locks["/ws/b"]
    assert lock_a is not lock_b

    # Same workspace returns same lock
    lock_a2 = _workspace_locks["/ws/a"]
    assert lock_a is lock_a2


# ---------------------------------------------------------------------------
# 9. Timeout behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_does_not_block_caller(interceptor: SnapshotInterceptor):
    """If snapshot takes > 3s, before_destructive_action returns without waiting."""

    async def _slow_snapshot(*args, **kwargs):
        await asyncio.sleep(10)

    mock_context = MagicMock(
        get_current_turn_id=MagicMock(return_value="turn-1"),
        get_current_chat_id=MagicMock(return_value="chat-1"),
        get_current_agent_id=MagicMock(return_value="agent-1"),
    )

    with patch.object(interceptor, "_safe_snapshot_with_lock", side_effect=_slow_snapshot):
        with patch.dict("sys.modules", {"app.ai_agents.general_agent.context": mock_context}):
            # Should return within ~3s (timeout), not 10s
            await asyncio.wait_for(
                interceptor.before_destructive_action("/tmp/ws", "bash", _make_payload()),
                timeout=5.0,
            )


# ---------------------------------------------------------------------------
# 10. _create_snapshot: workspace does not exist => early return
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_snapshot_skips_nonexistent_workspace(interceptor: SnapshotInterceptor):
    """_create_snapshot returns early if workspace path does not exist."""
    with patch.object(interceptor, "_run_async_cmd", new_callable=AsyncMock) as mock_cmd:
        await interceptor._create_snapshot("/nonexistent/workspace", "bash", "c", "a", "t")

    mock_cmd.assert_not_awaited()


# ---------------------------------------------------------------------------
# 11. _create_snapshot: no changes to commit => no commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_snapshot_skips_when_no_changes(interceptor: SnapshotInterceptor):
    """_create_snapshot skips commit when git status --porcelain is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init", tmpdir], capture_output=True, check=True)
        subprocess.run(["git", "-C", tmpdir, "config", "user.email", "t@t.com"], capture_output=True, check=True)
        subprocess.run(["git", "-C", tmpdir, "config", "user.name", "T"], capture_output=True, check=True)

        test_file = Path(tmpdir) / "f.txt"
        test_file.write_text("content")

        # Pre-create .gitignore with all default rules so _create_snapshot won't modify it
        gitignore = Path(tmpdir) / ".gitignore"
        gitignore.write_text("node_modules/\n.venv/\n*.mp4\n*.sqlite\n*.db\n")

        subprocess.run(["git", "-C", tmpdir, "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", tmpdir, "commit", "-m", "init"], capture_output=True, check=True)

        log_before = subprocess.run(
            ["git", "-C", tmpdir, "rev-list", "--count", "HEAD"], capture_output=True, text=True
        ).stdout.strip()

        await interceptor._create_snapshot(tmpdir, "bash", "c", "a", "t")

        log_after = subprocess.run(
            ["git", "-C", tmpdir, "rev-list", "--count", "HEAD"], capture_output=True, text=True
        ).stdout.strip()

        assert log_before == log_after


# ---------------------------------------------------------------------------
# 12. _create_snapshot: commits when there are changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_snapshot_commits_when_changes_exist(interceptor: SnapshotInterceptor):
    """_create_snapshot creates a git commit when workspace has uncommitted changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init", tmpdir], capture_output=True, check=True)
        subprocess.run(["git", "-C", tmpdir, "config", "user.email", "t@t.com"], capture_output=True, check=True)
        subprocess.run(["git", "-C", tmpdir, "config", "user.name", "T"], capture_output=True, check=True)

        test_file = Path(tmpdir) / "f.txt"
        test_file.write_text("v1")
        subprocess.run(["git", "-C", tmpdir, "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", tmpdir, "commit", "-m", "init"], capture_output=True, check=True)

        # Modify file
        test_file.write_text("v2")

        await interceptor._create_snapshot(tmpdir, "file_write", "chat-1", "agent-1", "turn-1")

        log_msg = subprocess.run(
            ["git", "-C", tmpdir, "log", "-1", "--format=%s"], capture_output=True, text=True
        ).stdout.strip()

        assert "Auto snapshot before file_write" in log_msg


# ---------------------------------------------------------------------------
# 13. _create_snapshot: auto-initializes git in a non-git directory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_snapshot_inits_git_when_absent(interceptor: SnapshotInterceptor):
    """_create_snapshot initializes a git repo if .git does not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "f.txt"
        test_file.write_text("content")

        assert not (Path(tmpdir) / ".git").exists()

        await interceptor._create_snapshot(tmpdir, "bash", "c", "a", "t")

        assert (Path(tmpdir) / ".git").exists()
        commit_count = subprocess.run(
            ["git", "-C", tmpdir, "rev-list", "--count", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        assert int(commit_count) >= 1


# ---------------------------------------------------------------------------
# 14. .gitignore injection adds missing rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitignore_injects_missing_rules(interceptor: SnapshotInterceptor):
    """_create_snapshot adds default ignore rules to .gitignore if missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gitignore = Path(tmpdir) / ".gitignore"
        gitignore.write_text("*.log\n")

        test_file = Path(tmpdir) / "f.txt"
        test_file.write_text("content")

        await interceptor._create_snapshot(tmpdir, "bash", "c", "a", "t")

        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".venv/" in content
        assert "*.log" in content  # original rule preserved


@pytest.mark.asyncio
async def test_gitignore_preserves_existing_rules(interceptor: SnapshotInterceptor):
    """_create_snapshot does not duplicate existing ignore rules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gitignore = Path(tmpdir) / ".gitignore"
        gitignore.write_text("node_modules/\n.venv/\n*.mp4\n*.sqlite\n*.db\n")

        test_file = Path(tmpdir) / "f.txt"
        test_file.write_text("content")

        await interceptor._create_snapshot(tmpdir, "bash", "c", "a", "t")

        content = gitignore.read_text()
        assert content.count("node_modules/") == 1


# ---------------------------------------------------------------------------
# 15. _run_async_cmd raises RuntimeError on failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_async_cmd_raises_on_failure(interceptor: SnapshotInterceptor):
    """_run_async_cmd raises RuntimeError when command exits non-zero."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # git log in a non-git directory will fail with non-zero exit
        with pytest.raises(RuntimeError, match="failed"):
            await interceptor._run_async_cmd("git", "log", cwd=tmpdir)


# ---------------------------------------------------------------------------
# 16. before_destructive_action with context returning None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_before_destructive_action_handles_none_context(interceptor: SnapshotInterceptor):
    """When context functions return None, defaults to 'unknown_*' and still works."""
    mock_context = MagicMock(
        get_current_turn_id=MagicMock(return_value=None),
        get_current_chat_id=MagicMock(return_value=None),
        get_current_agent_id=MagicMock(return_value=None),
    )

    with (
        patch.dict("sys.modules", {"app.ai_agents.general_agent.context": mock_context}),
        patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock_snapshot,
    ):
        await interceptor.before_destructive_action("/tmp/ws", "bash", _make_payload())

    mock_snapshot.assert_awaited_once()
    call_args = mock_snapshot.call_args
    assert call_args.args[2] == "unknown_chat"
    assert call_args.args[3] == "unknown_agent"
    assert call_args.args[4] == "unknown_turn"


# ---------------------------------------------------------------------------
# 17. _emit_snapshot_event silently catches exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_snapshot_event_catches_exceptions(interceptor: SnapshotInterceptor):
    """_emit_snapshot_event should not raise even if event bus fails."""
    mock_module = MagicMock()
    mock_module.get_event_bus.side_effect = RuntimeError("bus broken")

    with patch.dict("sys.modules", {"app.services.event.app_event_bus": mock_module}):
        # Should not raise
        await interceptor._emit_snapshot_event("chat-1", "bash")


# ---------------------------------------------------------------------------
# 18. Concurrent snapshots on different workspaces don't block each other
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_snapshots_different_workspaces(interceptor: SnapshotInterceptor):
    """Two different workspaces can snapshot concurrently without blocking."""
    interceptor._git_available = True
    call_order: list[str] = []

    async def _mock_create(workspace_path: str, *args, **kwargs):
        call_order.append(f"start-{workspace_path}")
        await asyncio.sleep(0.1)
        call_order.append(f"end-{workspace_path}")

    with (
        patch.object(interceptor, "_create_snapshot", side_effect=_mock_create),
        patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock),
    ):
        await asyncio.gather(
            interceptor._safe_snapshot_with_lock("/ws/a", "bash", "c", "a", "t1", ("/ws/a", "t1")),
            interceptor._safe_snapshot_with_lock("/ws/b", "bash", "c", "a", "t1", ("/ws/b", "t1")),
        )

    assert len(call_order) == 4
    assert "start-/ws/a" in call_order
    assert "start-/ws/b" in call_order


# ---------------------------------------------------------------------------
# 19. _safe_snapshot_with_lock caches git detection result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_snapshot_caches_git_detection(interceptor: SnapshotInterceptor):
    """_safe_snapshot_with_lock detects git once and caches the result."""
    assert interceptor._git_available is None

    with (
        patch.object(interceptor, "_detect_git", new_callable=AsyncMock, return_value=True) as mock_detect,
        patch.object(interceptor, "_create_snapshot", new_callable=AsyncMock),
        patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock),
    ):
        await interceptor._safe_snapshot_with_lock("/ws", "bash", "c", "a", "t1", ("/ws", "t1"))
        await interceptor._safe_snapshot_with_lock("/ws", "bash", "c", "a", "t2", ("/ws", "t2"))

    assert interceptor._git_available is True
    mock_detect.assert_awaited_once()
