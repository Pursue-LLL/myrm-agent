"""Tests for browser recording session manager."""

from __future__ import annotations

from myrm_agent_harness.toolkits.browser.action_capture.types import (
    ActionStep,
    ActionType,
    CaptureSession,
)

from app.services.browser_recording.session_manager import (
    get_session,
    get_session_export,
    list_active_sessions,
    register_session,
    remove_session,
)


def _fresh_session(session_id: str = "test-1") -> CaptureSession:
    return CaptureSession(session_id=session_id, start_url="https://example.com")


class TestSessionManager:
    def setup_method(self) -> None:
        from app.services.browser_recording import session_manager
        session_manager._sessions.clear()

    def test_register_and_get(self) -> None:
        session = _fresh_session()
        register_session(session)
        assert get_session("test-1") is session

    def test_get_missing_returns_none(self) -> None:
        assert get_session("nonexistent") is None

    def test_remove(self) -> None:
        session = _fresh_session()
        register_session(session)
        removed = remove_session("test-1")
        assert removed is session
        assert get_session("test-1") is None

    def test_remove_missing_returns_none(self) -> None:
        assert remove_session("nonexistent") is None

    def test_list_active_excludes_stopped(self) -> None:
        s1 = _fresh_session("active-1")
        s2 = _fresh_session("stopped-1")
        s2.status = "stopped"
        register_session(s1)
        register_session(s2)

        active = list_active_sessions()
        ids = [s["session_id"] for s in active]
        assert "active-1" in ids
        assert "stopped-1" not in ids

    def test_export_includes_steps(self) -> None:
        session = _fresh_session("export-1")
        session.add_step(ActionStep(
            seq=1,
            action=ActionType.CLICK,
            selector="#btn",
            url="https://example.com",
            element_text="Button",
            element_role="button",
        ))
        register_session(session)

        export = get_session_export("export-1")
        assert export is not None
        assert export["step_count"] == 1
        assert len(export["steps"]) == 1  # type: ignore[arg-type]

    def test_export_missing_returns_none(self) -> None:
        assert get_session_export("missing") is None
