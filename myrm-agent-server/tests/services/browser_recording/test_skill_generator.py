"""Tests for browser recording skill generator."""

from __future__ import annotations

from myrm_agent_harness.toolkits.browser.action_capture.types import (
    ActionStep,
    ActionType,
    CaptureSession,
)

from app.services.browser_recording.skill_generator import (
    generate_skill_from_session,
)


def _make_session(steps: list[ActionStep] | None = None) -> CaptureSession:
    session = CaptureSession(session_id="test-sess", start_url="https://example.com")
    session.status = "stopped"
    if steps:
        for s in steps:
            session.add_step(s)
    return session


def _make_step(
    seq: int,
    action: ActionType = ActionType.CLICK,
    is_password: bool = False,
    value: str = "",
) -> ActionStep:
    return ActionStep(
        seq=seq,
        action=action,
        selector=f"#el{seq}",
        value=value,
        url="https://example.com",
        element_text=f"Element {seq}",
        element_role="button",
        is_password=is_password,
    )


class TestGenerateSkillFromSession:
    def test_basic_generation(self) -> None:
        session = _make_session([
            _make_step(1, ActionType.NAVIGATE, value="https://example.com"),
            _make_step(2, ActionType.CLICK),
        ])

        skill_id, content, creds = generate_skill_from_session(
            session, "test-skill"
        )

        assert skill_id.startswith("recorded-test-skill-")
        assert "# test-skill" in content
        assert "test-sess" in content
        assert creds == []

    def test_auto_description(self) -> None:
        session = _make_session([_make_step(1)])
        _, content, _ = generate_skill_from_session(session, "my-skill")
        assert "https://example.com" in content

    def test_custom_description(self) -> None:
        session = _make_session([_make_step(1)])
        _, content, _ = generate_skill_from_session(
            session, "my-skill", description="Custom desc"
        )
        assert "Custom desc" in content

    def test_credential_detection(self) -> None:
        session = _make_session([
            _make_step(1, ActionType.TYPE, value="user@test.com"),
            _make_step(2, ActionType.TYPE, is_password=True, value="***"),
            _make_step(3, ActionType.CLICK),
        ])

        _, content, creds = generate_skill_from_session(session, "login-flow")

        assert len(creds) == 1
        assert "credential_step_2" in creds[0]
        assert "Credentials" in content
        assert "CredentialVault" in content

    def test_empty_session(self) -> None:
        session = _make_session()
        _, content, creds = generate_skill_from_session(session, "empty-skill")
        assert "# empty-skill" in content
        assert creds == []

    def test_allowed_tools_present(self) -> None:
        session = _make_session([_make_step(1)])
        _, content, _ = generate_skill_from_session(session, "s1")
        assert "allowed-tools" in content
        assert "browser_navigate" in content
