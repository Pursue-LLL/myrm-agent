"""AgentLifecycleMixin: what a turn releases, what dropping the agent releases, and that one failure never blocks the rest.

The mixin runs on its own here, holding only the attributes GeneralAgent gives it; the harness cleanup and the
settings it reads are the only things replaced.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai_agents.general_agent.lifecycle import AgentLifecycleMixin

LIFECYCLE_LOGGER = "app.ai_agents.general_agent.lifecycle"
POOL_REGISTRY = "app.services.external_agents.runtime_pool_registry"


class _Owner(AgentLifecycleMixin):
    """The mixin with the attributes GeneralAgent gives it, and nothing else."""

    def __init__(
        self,
        *,
        executor: object | None = None,
        chat_id: str | None = None,
        browser: object | None = None,
        agent: object | None = None,
    ) -> None:
        self._runtime_pool = None
        self._runtime_pool_scope_id = None
        self._runtime_pool_from_registry = False
        self._owned_runtime_pool = None
        self._executor = executor
        self._current_chat_id = chat_id
        self._browser_session = browser
        self.agent = agent


def _closer(calls: list[str], name: str, *, fails: bool = False) -> SimpleNamespace:
    """Something with an async ``close`` that records when it ran and may fail."""

    async def close() -> None:
        calls.append(name)
        if fails:
            raise RuntimeError(f"{name} failed")

    return SimpleNamespace(close=close)


@pytest.fixture
def cleanup(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The harness cleanup of the context files a session offloaded, observable."""
    cleanup_mock = AsyncMock()
    monkeypatch.setattr("myrm_agent_harness.runtime.context.offload.cleanup_session_context_files", cleanup_mock)
    return cleanup_mock


def _use_harness_dir(monkeypatch: pytest.MonkeyPatch, configured: str) -> None:
    settings = SimpleNamespace(database=SimpleNamespace(harness_dir=configured))
    monkeypatch.setattr("app.config.settings.get_settings", lambda: settings)


@pytest.fixture
def harness_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The directory recorded videos are made relative to."""
    _use_harness_dir(monkeypatch, str(tmp_path))
    return tmp_path


class TestReleasePooledSession:
    """What a turn frees; the pooled SkillAgent, browser and executor stay for the next turn."""

    async def test_cleans_the_context_files_its_executor_offloaded_and_keeps_everything_else(self, cleanup: AsyncMock) -> None:
        executor, browser, agent = (MagicMock(close=AsyncMock()) for _ in range(3))
        owner = _Owner(executor=executor, chat_id="chat-1", browser=browser, agent=agent)

        await owner.release_pooled_session()

        cleanup.assert_awaited_once_with("chat-1", executor)
        for kept in (executor, browser, agent):
            kept.close.assert_not_called()
        assert (owner._executor, owner._browser_session, owner.agent) == (executor, browser, agent)

    @pytest.mark.parametrize(
        ("executor", "chat_id"),
        [(None, "chat-1"), (MagicMock(), None), (None, None)],
        ids=["no-executor", "no-chat", "neither"],
    )
    async def test_cleans_nothing_without_both_an_executor_and_a_chat(
        self, cleanup: AsyncMock, executor: object | None, chat_id: str | None
    ) -> None:
        await _Owner(executor=executor, chat_id=chat_id).release_pooled_session()

        cleanup.assert_not_called()

    async def test_a_failing_context_cleanup_is_logged_and_never_fails_the_release(
        self, cleanup: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        cleanup.side_effect = RuntimeError("disk full")

        with caplog.at_level(logging.WARNING, logger=LIFECYCLE_LOGGER):
            await _Owner(executor=MagicMock(), chat_id="chat-1").release_pooled_session()

        assert "Context cleanup failed for chat_id=chat-1: disk full" in caplog.text

    async def test_a_failing_pool_release_is_logged_and_the_pool_is_forgotten(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        registry = MagicMock(release=AsyncMock(side_effect=RuntimeError("registry down")))
        monkeypatch.setattr(f"{POOL_REGISTRY}.get_chat_runtime_pool_registry", lambda: registry)
        owner = _Owner()
        owner._runtime_pool = MagicMock()
        owner._runtime_pool_scope_id = "chat-1"
        owner._runtime_pool_from_registry = True

        with caplog.at_level(logging.WARNING, logger=LIFECYCLE_LOGGER):
            await owner.release_pooled_session()

        registry.release.assert_awaited_once_with("chat-1")
        assert "RuntimePool release failed: registry down" in caplog.text
        assert owner._runtime_pool is None

    async def test_a_pool_neither_from_the_registry_nor_built_by_the_agent_is_only_forgotten(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        close_bounded = AsyncMock()
        monkeypatch.setattr(f"{POOL_REGISTRY}.close_runtime_pool_bounded", close_bounded)
        owner = _Owner()
        owner._runtime_pool = MagicMock()

        await owner.release_pooled_session()

        close_bounded.assert_not_called()
        assert owner._runtime_pool is None


class TestClose:
    """What dropping the agent frees: the browser, the executor and the harness SkillAgent."""

    async def test_releases_browser_then_executor_then_agent_and_forgets_them(
        self, cleanup: AsyncMock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        calls: list[str] = []
        cleanup.side_effect = lambda *_: calls.append("context files")
        owner = _Owner(
            executor=_closer(calls, "executor"),
            chat_id="chat-1",
            browser=_closer(calls, "browser"),
            agent=_closer(calls, "agent"),
        )
        # The video is only complete once the browser is closed, so the recording is read after it.
        monkeypatch.setattr(owner, "_capture_session_recording_info", lambda: calls.append("recording"))

        with caplog.at_level(logging.INFO, logger=LIFECYCLE_LOGGER):
            await owner.close()

        assert calls == ["browser", "recording", "context files", "executor", "agent"]
        assert (owner._executor, owner._browser_session, owner.agent) == (None, None, None)
        assert "Agent resources fully released" in caplog.text

    async def test_closes_an_executor_that_has_no_chat_without_the_context_cleanup(self, cleanup: AsyncMock) -> None:
        calls: list[str] = []
        owner = _Owner(executor=_closer(calls, "executor"))

        await owner.close()

        cleanup.assert_not_called()
        assert calls == ["executor"]

    @pytest.mark.parametrize("failing", ["browser", "executor", "agent"])
    async def test_one_failing_release_never_stops_the_next_and_is_forgotten_anyway(
        self, cleanup: AsyncMock, caplog: pytest.LogCaptureFixture, failing: str
    ) -> None:
        calls: list[str] = []
        owner = _Owner(
            executor=_closer(calls, "executor", fails=failing == "executor"),
            chat_id="chat-1",
            browser=_closer(calls, "browser", fails=failing == "browser"),
            agent=_closer(calls, "agent", fails=failing == "agent"),
        )

        with caplog.at_level(logging.WARNING, logger=LIFECYCLE_LOGGER):
            await owner.close()

        assert calls == ["browser", "executor", "agent"]
        assert (owner._executor, owner._browser_session, owner.agent) == (None, None, None)
        assert f"{failing} failed" in caplog.text

    async def test_a_failing_context_cleanup_never_keeps_the_executor_from_closing(
        self, cleanup: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        cleanup.side_effect = RuntimeError("disk full")
        calls: list[str] = []
        owner = _Owner(executor=_closer(calls, "executor"), chat_id="chat-1", agent=_closer(calls, "agent"))

        with caplog.at_level(logging.WARNING, logger=LIFECYCLE_LOGGER):
            await owner.close()

        assert calls == ["executor", "agent"]
        assert "Context cleanup failed for chat_id=chat-1: disk full" in caplog.text
        assert (owner._executor, owner.agent) == (None, None)


def _recording_owner(video_path: Path | str | None, *, enabled: bool = True) -> _Owner:
    observability = SimpleNamespace(recording_enabled=enabled, video_path=video_path)
    return _Owner(browser=SimpleNamespace(_observability=observability))


class TestSessionRecording:
    """The recorded browser session handed to the SSE stream once the browser is closed."""

    @pytest.mark.parametrize(
        "owner",
        [
            _Owner(),
            _Owner(browser=SimpleNamespace()),
            _recording_owner(None),
        ],
        ids=["no-browser", "no-observability", "no-video-path"],
    )
    def test_nothing_is_captured_without_a_recording(self, owner: _Owner) -> None:
        owner._capture_session_recording_info()

        assert not hasattr(owner, "_session_recording_info")

    def test_nothing_is_captured_when_recording_was_off_even_if_a_video_file_exists(self, tmp_path: Path) -> None:
        video = tmp_path / "session.webm"
        video.write_bytes(b"webm")
        owner = _recording_owner(video, enabled=False)

        owner._capture_session_recording_info()

        assert not hasattr(owner, "_session_recording_info")

    def test_nothing_is_captured_when_the_video_file_is_missing(self, tmp_path: Path) -> None:
        owner = _recording_owner(tmp_path / "missing.webm")

        owner._capture_session_recording_info()

        assert not hasattr(owner, "_session_recording_info")

    def test_a_video_under_the_harness_dir_is_previewed_by_its_relative_path(self, harness_dir: Path) -> None:
        video = harness_dir / "recordings" / "session.webm"
        video.parent.mkdir()
        video.write_bytes(b"webm")
        owner = _recording_owner(video)

        owner._capture_session_recording_info()

        assert owner._session_recording_info == {
            "filename": "session.webm",
            "preview_url": f"/api/v1/files/vault/render?filepath=recordings/session.webm&workspace={harness_dir}",
            "content_type": "video/webm",
        }

    def test_a_harness_dir_configured_with_a_trailing_slash_gives_the_same_relative_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_harness_dir(monkeypatch, f"{tmp_path}/")
        video = tmp_path / "recordings" / "session.webm"
        video.parent.mkdir()
        video.write_bytes(b"webm")
        owner = _recording_owner(video)

        owner._capture_session_recording_info()

        assert owner._session_recording_info["preview_url"] == (
            f"/api/v1/files/vault/render?filepath=recordings/session.webm&workspace={tmp_path}/"
        )

    def test_a_video_outside_the_harness_dir_keeps_its_full_path(
        self, harness_dir: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        video = tmp_path_factory.mktemp("elsewhere") / "session.webm"
        video.write_bytes(b"webm")
        owner = _recording_owner(video)

        owner._capture_session_recording_info()

        assert (
            owner._session_recording_info["preview_url"] == f"/api/v1/files/vault/render?filepath={video}&workspace={harness_dir}"
        )

    def test_a_failure_while_capturing_is_swallowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        video = tmp_path / "session.webm"
        video.write_bytes(b"webm")

        def unavailable() -> None:
            raise RuntimeError("settings unavailable")

        monkeypatch.setattr("app.config.settings.get_settings", unavailable)
        owner = _recording_owner(video)

        owner._capture_session_recording_info()

        assert not hasattr(owner, "_session_recording_info")
