"""Unit tests for LocalEvalExecutor workspace lifecycle cleanup.

Verifies that eval session workspaces are removed after a run and that the
startup orphan sweep clears leftovers from previous server runs:
- cleanup() removes every workspace the executor created (create_session and
  execute paths), is idempotent, and never touches another executor's sessions.
- cleanup_orphan_eval_workspaces() removes stale directories at boot only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.eval.executor import LocalEvalExecutor, cleanup_orphan_eval_workspaces


@pytest.mark.asyncio
async def test_cleanup_removes_created_session_workspaces(
    monkeypatch, tmp_path
) -> None:
    """cleanup must delete the physical workspace and reset executor state."""
    monkeypatch.chdir(tmp_path)

    executor = LocalEvalExecutor()
    session_id = await executor.create_session()
    workspace_dir = (Path(".myrm/eval_workspaces") / session_id).resolve()

    assert workspace_dir.is_dir()
    assert executor._session_id == session_id
    assert session_id in executor._sandbox_executors

    await executor.cleanup()

    assert not workspace_dir.exists()
    assert executor._session_id is None
    assert executor._sandbox_executors == {}
    assert executor._created_workspaces == set()


@pytest.mark.asyncio
async def test_cleanup_removes_implicit_execute_workspace(
    monkeypatch, tmp_path
) -> None:
    """An execute-only session (no create_session) still gets cleaned up.

    The executor registers the workspace it creates for an implicit chat id,
    so cleanup() must remove it even when the session was never materialized
    through create_session.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams
    from app.core.types import ModelConfig

    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    monkeypatch.chdir(tmp_path)

    executor = LocalEvalExecutor()
    chat_id = "eval_implicit_1234"

    with (
        patch("app.core.eval.executor.load_user_configs") as mock_load,
        patch(
            "app.core.eval.executor.AgentFactory.create_general_agent"
        ) as mock_factory,
    ):
        mock_cfg = MagicMock()
        mock_cfg.retrieval_dict = {}
        mock_cfg.mcp_dict = {}
        mock_cfg.providers_dict = {}
        mock_cfg.personal_settings_dict = {}
        mock_cfg.model_cfg = ModelConfig(model="test-model", api_key="key")
        mock_cfg.search_cfg = SearchServiceConfig(
            provider="tavily", searchService="tavily"
        )
        mock_cfg.search_is_user_configured = False
        mock_load.return_value = mock_cfg

        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield {"type": "message", "data": "ok"}

        mock_agent.process_stream = mock_stream
        mock_factory.return_value = mock_agent

        await executor.execute("hello", session_id=chat_id)

    workspace_dir = (Path(".myrm/eval_workspaces") / chat_id).resolve()
    assert workspace_dir.is_dir()
    assert workspace_dir in executor._created_workspaces

    await executor.cleanup()

    assert not workspace_dir.exists()
    assert executor._created_workspaces == set()


@pytest.mark.asyncio
async def test_cleanup_is_idempotent(monkeypatch, tmp_path) -> None:
    """Repeated cleanup (and cleanup with no sessions) must be a no-op."""
    monkeypatch.chdir(tmp_path)

    executor = LocalEvalExecutor()
    await executor.cleanup()
    await executor.cleanup()

    await executor.create_session()
    await executor.cleanup()
    await executor.cleanup()


@pytest.mark.asyncio
async def test_cleanup_only_removes_own_sessions(monkeypatch, tmp_path) -> None:
    """cleanup must not delete workspaces owned by another executor."""
    monkeypatch.chdir(tmp_path)

    executor_a = LocalEvalExecutor()
    executor_b = LocalEvalExecutor()
    session_a = await executor_a.create_session()
    session_b = await executor_b.create_session()

    workspace_a = (Path(".myrm/eval_workspaces") / session_a).resolve()
    workspace_b = (Path(".myrm/eval_workspaces") / session_b).resolve()

    await executor_a.cleanup()

    assert not workspace_a.exists()
    assert workspace_b.is_dir()


@pytest.mark.asyncio
async def test_cleanup_handles_missing_workspace(monkeypatch, tmp_path) -> None:
    """cleanup must survive a workspace deleted externally (e.g. by the OS)."""
    monkeypatch.chdir(tmp_path)

    executor = LocalEvalExecutor()
    await executor.create_session()
    for workspace_dir in list(executor._created_workspaces):
        workspace_dir.rmdir() if workspace_dir.is_dir() else None

    await executor.cleanup()

    assert executor._created_workspaces == set()
    assert executor._sandbox_executors == {}


def test_cleanup_orphan_eval_workspaces_removes_leftovers(
    monkeypatch, tmp_path
) -> None:
    """Startup sweep must remove every stale session directory and count them."""
    root = Path(tmp_path / ".myrm" / "eval_workspaces")
    root.mkdir(parents=True)
    (root / "eval_orphan1").mkdir()
    (root / "eval_orphan2").mkdir()

    monkeypatch.chdir(tmp_path)
    count = cleanup_orphan_eval_workspaces()

    assert count == 2
    assert not root.exists()


def test_cleanup_orphan_eval_workspaces_noop_when_absent(monkeypatch, tmp_path) -> None:
    """Startup sweep must return 0 when no eval workspaces exist."""
    monkeypatch.chdir(tmp_path)
    assert cleanup_orphan_eval_workspaces() == 0


def test_cleanup_orphan_skips_non_directory_entries(monkeypatch, tmp_path) -> None:
    """A stray file under the sweep root must be skipped, not treated as a session."""
    monkeypatch.chdir(tmp_path)
    root = Path(".myrm/eval_workspaces")
    root.mkdir(parents=True)
    (root / "eval_orphan").mkdir()
    (root / "stray.log").write_text("not a workspace")

    count = cleanup_orphan_eval_workspaces()

    assert count == 1
    assert not (root / "eval_orphan").exists()
    assert (root / "stray.log").exists()


def test_cleanup_orphan_swallow_rmdir_failure(monkeypatch, tmp_path) -> None:
    """A sweep root that refuses deletion must not raise (best-effort sweep)."""
    monkeypatch.chdir(tmp_path)
    root = Path(".myrm/eval_workspaces")
    root.mkdir(parents=True)
    (root / "eval_orphan").mkdir()

    import app.core.eval.executor as executor_mod

    def failing_rmdir(self: Path) -> None:
        raise OSError("directory not empty")

    monkeypatch.setattr(Path, "rmdir", failing_rmdir)
    count = executor_mod.cleanup_orphan_eval_workspaces()

    assert count == 1
    assert root.exists()
