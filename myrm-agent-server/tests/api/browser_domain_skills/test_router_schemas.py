"""Unit tests for browser_domain_skills router schemas and helpers.

Covers Pydantic validation (DistillSkillRequest path-safety, field constraints)
and the _manifest_to_response helper. No server/network required.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.browser_domain_skills.router import (
    DistillSkillRequest,
    DistillToolInput,
    DomainSkillResponse,
    DomainToolResponse,
    _manifest_to_response,
)


# ---------------------------------------------------------------------------
# DistillSkillRequest — tool_name path-safety validation
# ---------------------------------------------------------------------------


class TestDistillSkillRequestValidation:
    def test_valid_request_accepted(self) -> None:
        req = DistillSkillRequest(
            skill_id="my-skill",
            name="My Skill",
            domains=["example.com"],
            tools={
                "fetch_page": DistillToolInput(
                    description="Fetch",
                    script_content="async def fetch_page(s, a): pass",
                    callable_name="fetch_page",
                ),
            },
        )
        assert req.skill_id == "my-skill"
        assert "fetch_page" in req.tools

    def test_path_traversal_tool_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid tool name"):
            DistillSkillRequest(
                skill_id="evil",
                name="Evil",
                domains=["evil.com"],
                tools={
                    "../../backdoor": DistillToolInput(
                        description="x",
                        script_content="x",
                        callable_name="x",
                    ),
                },
            )

    def test_uppercase_tool_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid tool name"):
            DistillSkillRequest(
                skill_id="bad",
                name="Bad",
                domains=["bad.com"],
                tools={
                    "GetData": DistillToolInput(
                        description="x",
                        script_content="x",
                        callable_name="x",
                    ),
                },
            )

    def test_hyphen_tool_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid tool name"):
            DistillSkillRequest(
                skill_id="bad",
                name="Bad",
                domains=["bad.com"],
                tools={
                    "get-data": DistillToolInput(
                        description="x",
                        script_content="x",
                        callable_name="x",
                    ),
                },
            )

    def test_underscore_prefix_tool_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid tool name"):
            DistillSkillRequest(
                skill_id="bad",
                name="Bad",
                domains=["bad.com"],
                tools={
                    "_private": DistillToolInput(
                        description="x",
                        script_content="x",
                        callable_name="x",
                    ),
                },
            )

    def test_empty_domains_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DistillSkillRequest(
                skill_id="ok",
                name="Ok",
                domains=[],
                tools={},
            )

    def test_empty_skill_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DistillSkillRequest(
                skill_id="",
                name="X",
                domains=["x.com"],
                tools={},
            )

    def test_invalid_skill_id_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DistillSkillRequest(
                skill_id="../../evil",
                name="Evil",
                domains=["evil.com"],
                tools={},
            )

    def test_empty_tools_accepted(self) -> None:
        req = DistillSkillRequest(
            skill_id="minimal",
            name="Minimal",
            domains=["minimal.com"],
            tools={},
        )
        assert len(req.tools) == 0

    def test_multiple_valid_tools_accepted(self) -> None:
        req = DistillSkillRequest(
            skill_id="multi",
            name="Multi",
            domains=["multi.com"],
            tools={
                "tool1": DistillToolInput(
                    description="T1",
                    script_content="pass",
                    callable_name="t1",
                ),
                "tool2": DistillToolInput(
                    description="T2",
                    script_content="pass",
                    callable_name="t2",
                ),
            },
        )
        assert len(req.tools) == 2


# ---------------------------------------------------------------------------
# DistillToolInput field constraints
# ---------------------------------------------------------------------------


class TestDistillToolInputValidation:
    def test_empty_script_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DistillToolInput(
                description="x",
                script_content="",
                callable_name="x",
            )

    def test_empty_callable_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DistillToolInput(
                description="x",
                script_content="pass",
                callable_name="",
            )


# ---------------------------------------------------------------------------
# _manifest_to_response helper
# ---------------------------------------------------------------------------


class TestManifestToResponse:
    def test_basic_conversion(self) -> None:
        from myrm_agent_harness.toolkits.browser.domain_skills import (
            DomainSkillManifest,
            DomainTool,
        )

        tool = DomainTool(
            name="echo",
            description="Echo back",
            script_path="tools/echo.py",
            callable_name="echo",
            args={"msg": {"type": "string", "required": "true"}},
            returns_description="echoed message",
        )
        manifest = DomainSkillManifest(
            id="test-skill",
            name="Test Skill",
            domains=("test.com", "*.test.com"),
            python_tools={"echo": tool},
        )

        resp = _manifest_to_response(manifest)
        assert isinstance(resp, DomainSkillResponse)
        assert resp.id == "test-skill"
        assert resp.name == "Test Skill"
        assert resp.domains == ["test.com", "*.test.com"]
        assert resp.is_builtin is False
        assert "echo" in resp.python_tools
        echo_resp = resp.python_tools["echo"]
        assert isinstance(echo_resp, DomainToolResponse)
        assert echo_resp.callable_name == "echo"
        assert echo_resp.returns_description == "echoed message"

    def test_builtin_flag_propagation(self) -> None:
        from myrm_agent_harness.toolkits.browser.domain_skills import (
            DomainSkillManifest,
        )

        manifest = DomainSkillManifest(
            id="builtin-test",
            name="Builtin",
            domains=("b.com",),
        )
        resp = _manifest_to_response(manifest, builtin=True)
        assert resp.is_builtin is True

    def test_empty_tools(self) -> None:
        from myrm_agent_harness.toolkits.browser.domain_skills import (
            DomainSkillManifest,
        )

        manifest = DomainSkillManifest(
            id="empty",
            name="Empty",
            domains=("e.com",),
        )
        resp = _manifest_to_response(manifest)
        assert resp.python_tools == {}
