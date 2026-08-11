"""Tests for browser recording skill generator."""

from __future__ import annotations

from myrm_agent_harness.api.skills import parse_skill_frontmatter
from myrm_agent_harness.toolkits.browser.action_capture.types import (
    ActionStep,
    ActionType,
    CaptureSession,
)

from app.services.browser_recording.skill_generator import (
    generate_skill_from_session,
)


def _make_session(steps: list[ActionStep] | None = None, start_url: str = "https://example.com") -> CaptureSession:
    session = CaptureSession(session_id="test-sess", start_url=start_url)
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
    element_text: str = "Element {seq}",
    element_role: str = "button",
) -> ActionStep:
    return ActionStep(
        seq=seq,
        action=action,
        selector=f"#el{seq}",
        value=value,
        url="https://example.com",
        element_text=element_text.format(seq=seq),
        element_role=element_role,
        is_password=is_password,
    )


class TestGenerateSkillFromSession:
    def test_basic_generation(self) -> None:
        session = _make_session(
            [
                _make_step(1, ActionType.NAVIGATE, value="https://example.com"),
                _make_step(2, ActionType.CLICK),
            ]
        )

        skill_id, content, creds = generate_skill_from_session(session, "test-skill")

        assert skill_id.startswith("recorded-test-skill-")
        assert "# test-skill" in content
        assert "Start URL: https://example.com" in content
        assert "test-sess" not in content
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
        session = _make_session(
            [
                _make_step(1, ActionType.FILL, value="user@test.com"),
                _make_step(
                    2,
                    ActionType.FILL,
                    is_password=True,
                    value="***",
                    element_text="Password",
                ),
                _make_step(3, ActionType.CLICK),
            ]
        )

        _, content, creds = generate_skill_from_session(session, "login-flow")

        assert len(creds) == 1
        assert creds[0] == "example.com-password"
        assert "Credentials" in content
        assert 'fill_credential "example.com-password"' in content
        assert "provides the real value automatically" in content
        assert "CredentialVault" not in content

    def test_click_on_sensitive_field_is_not_credential(self) -> None:
        session = _make_session(
            [
                _make_step(
                    1, ActionType.CLICK, is_password=True, element_text="Password"
                ),
                _make_step(
                    2,
                    ActionType.FILL,
                    is_password=True,
                    value="***",
                    element_text="Password",
                ),
            ]
        )

        _, content, creds = generate_skill_from_session(session, "click-then-fill")

        assert creds == ["example.com-password"]
        assert content.count("Fill credential") == 1
        assert '1. Click on "Password"' in content

    def test_credential_labels_are_semantic_and_unique(self) -> None:
        session = _make_session(
            [
                _make_step(
                    1,
                    ActionType.FILL,
                    is_password=True,
                    value="***",
                    element_text="Password",
                ),
                _make_step(
                    2,
                    ActionType.FILL,
                    is_password=True,
                    value="***",
                    element_text="Password",
                ),
            ]
        )

        _, content, creds = generate_skill_from_session(session, "dupe-login")

        assert creds == ["example.com-password", "example.com-password-2"]
        assert 'fill_credential "example.com-password"' in content
        assert 'fill_credential "example.com-password-2"' in content

    def test_credential_labels_are_site_scoped(self) -> None:
        password_step = _make_step(
            1,
            ActionType.FILL,
            is_password=True,
            value="***",
            element_text="Password",
        )
        session_a = _make_session([password_step], start_url="https://gitlab.example.com")
        session_b = _make_session([password_step], start_url="https://oa.example.com")

        _, _, creds_a = generate_skill_from_session(session_a, "gitlab-login")
        _, _, creds_b = generate_skill_from_session(session_b, "oa-login")

        assert creds_a == ["gitlab.example.com-password"]
        assert creds_b == ["oa.example.com-password"]

    def test_credential_label_falls_back_without_host(self) -> None:
        session = _make_session(
            [
                _make_step(
                    1,
                    ActionType.FILL,
                    is_password=True,
                    value="***",
                    element_text="Password",
                ),
            ],
            start_url="not-a-url",
        )

        _, content, creds = generate_skill_from_session(session, "no-host-login")

        assert creds == ["site-password"]
        assert 'fill_credential "site-password"' in content

    def test_empty_session(self) -> None:
        session = _make_session()
        _, content, creds = generate_skill_from_session(session, "empty-skill")
        assert "# empty-skill" in content
        assert creds == []

    def test_fill_step_includes_element_context(self) -> None:
        session = _make_session(
            [
                _make_step(
                    1,
                    ActionType.FILL,
                    value="Alice",
                    element_text="Username",
                    element_role="textbox",
                ),
            ]
        )

        _, content, _ = generate_skill_from_session(session, "form-fill")

        assert 'Fill "Alice" into textbox "Username"' in content

    def test_select_step_includes_option_labels(self) -> None:
        session = _make_session(
            [
                _make_step(1, ActionType.NAVIGATE, value="https://example.com"),
                ActionStep(
                    seq=2,
                    action=ActionType.SELECT,
                    selector="#lang",
                    value="en; zh",
                    label="English, Chinese",
                    url="https://example.com",
                    element_text="Language",
                    element_role="select",
                ),
            ]
        )

        _, content, _ = generate_skill_from_session(session, "multi-select-flow")

        assert 'Select "en; zh" (English, Chinese)' in content
        assert "from dropdown" not in content

    def test_select_single_value_keeps_dropdown_template(self) -> None:
        session = _make_session(
            [
                _make_step(
                    1,
                    ActionType.SELECT,
                    value="en",
                    element_text="Language",
                    element_role="select",
                ),
            ]
        )

        _, content, _ = generate_skill_from_session(session, "single-select")

        assert 'Select "en" from dropdown' in content

    def test_allowed_tools_use_registered_names(self) -> None:
        session = _make_session([_make_step(1)])
        _, content, _ = generate_skill_from_session(session, "s1")

        assert "allowed-tools" in content
        for tool in (
            "browser_navigate_tool",
            "browser_interact_tool",
            "browser_snapshot_tool",
            "browser_extract_tool",
            "browser_manage_tool",
        ):
            assert tool in content

        for bogus in (
            "browser_navigate,",
            "browser_click",
            "browser_fill",
            "browser_select",
        ):
            assert bogus not in content

    def test_generated_content_has_valid_frontmatter(self) -> None:
        session = _make_session(
            [
                _make_step(1, ActionType.NAVIGATE, value="https://example.com"),
                _make_step(
                    2,
                    ActionType.FILL,
                    value="Alice",
                    element_text="Username",
                    element_role="textbox",
                ),
            ]
        )
        _, content, _ = generate_skill_from_session(
            session, "login-skill", description="Automate login"
        )

        fm = parse_skill_frontmatter(content, "login-skill")
        assert fm.name == "login-skill"
        assert fm.description == "Automate login"
        assert fm.allowed_tools == (
            "browser_navigate_tool browser_interact_tool browser_snapshot_tool "
            "browser_extract_tool browser_manage_tool"
        )

    def test_frontmatter_description_tolerates_newlines(self) -> None:
        session = _make_session([_make_step(1)])
        _, content, _ = generate_skill_from_session(
            session,
            "multi-line-skill",
            description='Line one\nLine two with "quotes"',
        )

        fm = parse_skill_frontmatter(content, "multi-line-skill")
        assert "Line one" in fm.description
        assert "quotes" in fm.description
