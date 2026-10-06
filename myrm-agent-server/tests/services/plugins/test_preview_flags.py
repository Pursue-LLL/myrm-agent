"""Preview facts: what confirm would block, conflict with, withhold or fail to resolve."""

from __future__ import annotations

from myrm_agent_harness.agent.plugins.models import (
    AgentPluginManifestMeta,
    PluginAgent,
    PluginMcpServer,
    PluginParseResult,
    PluginSkill,
)
from myrm_agent_harness.agent.plugins.rules import MAX_TEMPLATE_FILE_BYTES, MAX_TOTAL_TEMPLATE_BYTES

from app.services.plugins._preview import build_preview_result
from app.services.plugins._preview_context import ExistingExpert, ExistingSkill, PreviewContext


def _skill(name: str) -> PluginSkill:
    return PluginSkill(name=name, description="d", content="body", files={"SKILL.md": b"body"})


def _server(name: str, server_type: str = "stdio") -> PluginMcpServer:
    return PluginMcpServer(
        name=name,
        server_type=server_type,
        command="node" if server_type == "stdio" else None,
        args=None,
        url="https://x.example/mcp" if server_type != "stdio" else None,
        headers=None,
        cwd=None,
    )


def _result(
    *,
    skills: list[PluginSkill] | None = None,
    servers: list[PluginMcpServer] | None = None,
    agents: list[PluginAgent] | None = None,
    workspace_files: dict[str, bytes] | None = None,
) -> PluginParseResult:
    return PluginParseResult(
        meta=AgentPluginManifestMeta(name="pkg", version="1.0.0"),
        skills=skills or [],
        servers=servers or [],
        agents=agents or [],
        workspace_files=workspace_files or {},
    )


class TestDeploymentAwareness:
    def test_nothing_is_blocked_without_installation_state(self) -> None:
        preview = build_preview_result(_result(skills=[_skill("a")], servers=[_server("s")]))

        assert preview["deployment"] == {"allows_local_skills": True, "allow_stdio": True}
        assert preview["skills"][0]["blocked_reason"] is None
        assert preview["servers"][0]["blocked_reason"] is None

    def test_deployment_limits_are_reported_per_component(self) -> None:
        context = PreviewContext(allows_local_skills=False, allow_stdio=False)

        preview = build_preview_result(
            _result(skills=[_skill("a")], servers=[_server("local"), _server("remote", "streamable_http")]), context
        )

        assert preview["deployment"] == {"allows_local_skills": False, "allow_stdio": False}
        assert preview["skills"][0]["blocked_reason"] == "skills_not_supported"
        assert preview["skills"][0]["security_issues"] == []  # blocked skills are not scanned
        assert [s["blocked_reason"] for s in preview["servers"]] == ["stdio_not_allowed", None]

    def test_same_name_skill_conflicts_regardless_of_case(self) -> None:
        context = PreviewContext(local_skills={"report-writer": ExistingSkill("local::abc", "1.4.0", "agent-plugin")})

        preview = build_preview_result(_result(skills=[_skill("Report-Writer"), _skill("other")]), context)

        assert [s["conflict"] for s in preview["skills"]] == [True, False]

    def test_conflict_shows_the_installed_version_and_source(self) -> None:
        context = PreviewContext(
            local_skills={
                "report-writer": ExistingSkill("local::abc", "1.4.0", "agent-plugin"),
                "handmade": ExistingSkill("local::def", None, None),
            }
        )

        skills = build_preview_result(_result(skills=[_skill("report-writer"), _skill("handmade"), _skill("new")]), context)[
            "skills"
        ]

        assert [(s["existing_version"], s["existing_source"]) for s in skills] == [
            ("1.4.0", "agent-plugin"),
            (None, None),
            (None, None),
        ]


class TestExpertFacts:
    def test_tighten_only_effects_are_visible_before_import(self) -> None:
        agent = PluginAgent(name="Lead", max_iterations=400, tool_names=("web_search", "browser"), is_entry_agent=True)

        expert = build_preview_result(_result(agents=[agent]))["agents"][0]

        assert expert["max_iterations"] == 400
        assert expert["effective_max_iterations"] == 50
        assert expert["granted_tools"] == ["web_search"]
        assert expert["withheld_tools"] == ["browser"]

    def test_same_name_expert_is_reported_with_its_identity(self) -> None:
        context = PreviewContext(
            experts_by_name={
                "lead": ExistingExpert("mine-1", is_built_in=False),
                "helper": ExistingExpert("builtin", is_built_in=True),
            }
        )
        agents = [PluginAgent(name=" Lead "), PluginAgent(name="Helper"), PluginAgent(name="Fresh")]

        experts = build_preview_result(_result(agents=agents), context)["agents"]

        assert [(e["conflict"], e["existing_agent_id"], e["existing_is_built_in"]) for e in experts] == [
            (True, "mine-1", False),
            (True, "builtin", True),
            (False, None, False),
        ]

    def test_references_that_will_not_resolve_are_listed(self) -> None:
        agent = PluginAgent(
            name="Lead",
            skill_names=("Bundled", "installed", "ghost"),
            mcp_names=("srv", "configured", "nope"),
            subagent_names=("Helper", "Missing", "Lead"),
            is_entry_agent=True,
        )
        result = _result(
            agents=[agent, PluginAgent(name="Helper", is_subagent=True)],
            skills=[_skill("bundled")],
            servers=[_server("srv")],
        )
        context = PreviewContext(skill_ids_by_name={"installed": "local::abc"}, server_names=frozenset({"configured"}))

        expert = build_preview_result(result, context)["agents"][0]

        assert expert["unresolved_skills"] == ["ghost"]
        assert expert["unresolved_connectors"] == ["nope"]
        assert expert["unresolved_subagents"] == ["Missing", "Lead"]  # unknown, and an expert cannot lead itself


class TestTemplateDiagnostics:
    def test_oversized_file_is_flagged(self) -> None:
        result = _result(workspace_files={"big.bin": b"x" * (MAX_TEMPLATE_FILE_BYTES + 1)})

        diagnostics = build_preview_result(result)["diagnostics"]

        assert [d["code"] for d in diagnostics] == ["OVERSIZED_TEMPLATE_FILE"]
        assert "big.bin" in diagnostics[0]["message"]

    def test_cumulative_ceiling_is_flagged_for_the_overflowing_file_only(self) -> None:
        files: dict[str, bytes] = {}
        remaining = MAX_TOTAL_TEMPLATE_BYTES - 100
        index = 0
        while remaining > 0:
            size = min(MAX_TEMPLATE_FILE_BYTES, remaining)
            files[f"part{index}.txt"] = b"a" * size
            remaining -= size
            index += 1
        files["over.txt"] = b"b" * 200

        diagnostics = build_preview_result(_result(workspace_files=files))["diagnostics"]

        assert [(d["code"], d["component"]) for d in diagnostics] == [("OVERSIZED_WORKSPACE_TOTAL", "workspace:over.txt")]
