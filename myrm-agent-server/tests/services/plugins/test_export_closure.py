"""Dependency closure of an exported expert: what ships, what is referenced by name, what is reported."""

from __future__ import annotations

import pytest

from app.services.plugins import _export_closure
from app.services.plugins._export_closure import build_export_plan
from app.services.plugins._export_models import ExportError, ExportErrorCode, ExportPlan, Omit, OmittedItem
from app.services.plugins.template_workspace import TEMPLATE_FILES_KEY, encode_template_files
from tests.support.export_world import SKILL_MD, ExportWorld


def _omitted(plan: ExportPlan) -> set[tuple[str, str, Omit]]:
    return {(item.kind, item.name, item.reason) for item in plan.omitted}


def _reasons(plan: ExportPlan, kind: str) -> dict[str, Omit]:
    return {item.name: item.reason for item in plan.omitted if item.kind == kind}


class TestRefusals:
    @pytest.mark.asyncio
    async def test_unknown_expert(self, world: ExportWorld) -> None:
        with pytest.raises(ExportError) as caught:
            await build_export_plan("missing")
        assert caught.value.code is ExportErrorCode.EXPERT_NOT_FOUND

    @pytest.mark.asyncio
    async def test_built_in_expert_cannot_be_exported(self, world: ExportWorld) -> None:
        world.expert("general", "General", built_in=True)
        with pytest.raises(ExportError) as caught:
            await build_export_plan("general")
        assert caught.value.code is ExportErrorCode.BUILT_IN_EXPERT


class TestExpertGraph:
    @pytest.mark.asyncio
    async def test_sub_experts_follow_the_entry_expert_and_reference_each_other_by_name(self, world: ExportWorld) -> None:
        world.expert("lead", "Lead", subagents=("worker",))
        world.expert("worker", "Worker")

        plan = await build_export_plan("lead")

        lead, worker = (draft.agent for draft in plan.experts)
        assert (lead.name, lead.is_entry_agent, lead.is_subagent, lead.subagent_names) == ("Lead", True, False, ("Worker",))
        assert (worker.name, worker.is_entry_agent, worker.is_subagent) == ("Worker", False, True)
        assert plan.plugin_name == "lead"

    @pytest.mark.asyncio
    async def test_a_link_back_to_a_parent_is_dropped_and_reported(self, world: ExportWorld) -> None:
        world.expert("a", "A", subagents=("b",))
        world.expert("b", "B", subagents=("c",))
        world.expert("c", "C", subagents=("a", "b"))

        plan = await build_export_plan("a")

        names = {draft.agent.name: draft.agent.subagent_names for draft in plan.experts}
        assert names == {"A": ("B",), "B": ("C",), "C": ()}
        assert _reasons(plan, "expert") == {"a": Omit.EXPERT_CYCLE, "b": Omit.EXPERT_CYCLE}

    @pytest.mark.asyncio
    async def test_a_shared_sub_expert_is_exported_once(self, world: ExportWorld) -> None:
        world.expert("a", "A", subagents=("b", "c"))
        world.expert("b", "B", subagents=("d",))
        world.expert("c", "C", subagents=("d",))
        world.expert("d", "D")

        plan = await build_export_plan("a")

        assert sorted(draft.agent.name for draft in plan.experts) == ["A", "B", "C", "D"]
        by_name = {draft.agent.name: draft.agent.subagent_names for draft in plan.experts}
        assert by_name["B"] == by_name["C"] == ("D",)
        assert not plan.omitted

    @pytest.mark.asyncio
    async def test_built_in_and_missing_sub_experts_are_reported(self, world: ExportWorld) -> None:
        world.expert("lead", "Lead", subagents=("builtin", "gone", "mine"))
        world.expert("builtin", "General", built_in=True)
        world.expert("mine", "Mine")

        plan = await build_export_plan("lead")

        assert [draft.agent.name for draft in plan.experts] == ["Lead", "Mine"]
        assert plan.entry.subagent_names == ("Mine",)
        assert _reasons(plan, "expert") == {"General": Omit.EXPERT_BUILT_IN, "gone": Omit.EXPERT_MISSING}

    @pytest.mark.asyncio
    async def test_same_display_names_stay_distinct_because_experts_reference_by_name(self, world: ExportWorld) -> None:
        world.expert("lead", "Helper", subagents=("h2", "h3"))
        world.expert("h2", "helper")
        world.expert("h3", "HELPER")

        plan = await build_export_plan("lead")

        assert [draft.agent.name for draft in plan.experts] == ["Helper", "helper (2)", "HELPER (3)"]
        assert plan.entry.subagent_names == ("helper (2)", "HELPER (3)")

    @pytest.mark.asyncio
    async def test_the_expert_count_is_bounded(self, world: ExportWorld, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_export_closure, "MAX_EXPORT_EXPERTS", 2)
        world.expert("a", "A", subagents=("b", "c"))
        world.expert("b", "B")
        world.expert("c", "C")

        plan = await build_export_plan("a")

        assert [draft.agent.name for draft in plan.experts] == ["A", "B"]
        assert _reasons(plan, "expert") == {"C": Omit.TOO_MANY_EXPERTS}


class TestSkills:
    @pytest.mark.asyncio
    async def test_custom_skills_ship_with_files_and_presets_travel_by_name(self, world: ExportWorld) -> None:
        world.custom_skill(
            "local::a1", "Report Writer", {"SKILL.md": SKILL_MD, "scripts/run.py": b"print(1)\n"}, directory="report-writer"
        )
        world.preset_skill("web-research", "web-research")
        world.expert("lead", "Lead", skills=("local::a1", "web-research"))

        plan = await build_export_plan("lead")

        assert plan.entry.skill_names == ("report-writer", "web-research")
        (skill,) = plan.skills
        assert (skill.package_name, skill.display_name, sorted(skill.files)) == (
            "report-writer",
            "Report Writer",
            ["SKILL.md", "scripts/run.py"],
        )
        assert plan.preset_skill_names == ["web-research"]

    @pytest.mark.asyncio
    async def test_a_skill_shared_by_experts_ships_once(self, world: ExportWorld) -> None:
        world.custom_skill("local::a1", "writer", directory="writer")
        world.expert("lead", "Lead", skills=("local::a1",), subagents=("worker",))
        world.expert("worker", "Worker", skills=("local::a1",))

        plan = await build_export_plan("lead")

        assert [skill.package_name for skill in plan.skills] == ["writer"]
        assert all(draft.agent.skill_names == ("writer",) for draft in plan.experts)

    @pytest.mark.asyncio
    async def test_a_binding_made_from_a_skill_folder_name_resolves(self, world: ExportWorld) -> None:
        world.custom_skill("local::a1", "writer", directory="writer")
        world.expert("lead", "Lead", skills=("Writer",))

        plan = await build_export_plan("lead")

        assert plan.entry.skill_names == ("writer",)

    @pytest.mark.asyncio
    async def test_provenance_of_third_party_skills_is_recorded(self, world: ExportWorld) -> None:
        world.custom_skill("local::a1", "mine", directory="mine")
        world.custom_skill("local::b2", "borrowed", directory="borrowed", source="clawhub")
        world.expert("lead", "Lead", skills=("local::a1", "local::b2"))

        plan = await build_export_plan("lead")

        assert {skill.package_name: skill.origin_source for skill in plan.skills} == {"mine": None, "borrowed": "clawhub"}

    @pytest.mark.asyncio
    async def test_unavailable_skills_are_reported(self, world: ExportWorld) -> None:
        world.custom_skill("local::empty", "empty", {}, directory="empty")
        world.custom_skill("local::nomd", "nomd", {"notes.txt": b"x"}, directory="nomd")
        world.expert("lead", "Lead", skills=("local::empty", "local::nomd", "local::gone"))

        plan = await build_export_plan("lead")

        assert plan.skills == []
        assert plan.entry.skill_names == ()
        assert _reasons(plan, "skill") == {
            "empty": Omit.SKILL_UNAVAILABLE,
            "nomd": Omit.SKILL_UNAVAILABLE,
            "local::gone": Omit.SKILL_UNAVAILABLE,
        }

    @pytest.mark.asyncio
    async def test_files_that_cannot_be_reviewed_or_must_not_travel_are_reported_not_shipped(self, world: ExportWorld) -> None:
        world.custom_skill(
            "local::a1",
            "tools",
            {
                "SKILL.md": SKILL_MD,
                "notes.md": b"fine",
                "bin/helper": b"\x7fELF\x00\x01binary",
                "data/blob.txt": b"\xff\xfe invalid utf8",
                "data/huge.csv": b"x" * (_export_closure.MAX_SKILL_FILE_BYTES + 1),
                ".env": b"API_KEY=real",
                "node_modules/pkg/index.js": b"1",
                "../escape.md": b"x",
            },
            directory="tools",
        )
        world.expert("lead", "Lead", skills=("local::a1",))

        plan = await build_export_plan("lead")

        assert sorted(plan.skills[0].files) == ["SKILL.md", "notes.md"]
        assert _reasons(plan, "skill_file") == {
            "tools/bin/helper": Omit.BINARY_FILE,
            "tools/data/blob.txt": Omit.BINARY_FILE,
            "tools/data/huge.csv": Omit.OVERSIZED_FILE,
            "tools/.env": Omit.EXCLUDED_PATH,
            "tools/node_modules/pkg/index.js": Omit.EXCLUDED_PATH,
            "tools/../escape.md": Omit.EXCLUDED_PATH,
        }

    @pytest.mark.asyncio
    async def test_the_reviewed_text_budget_is_bounded(self, world: ExportWorld, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_export_closure, "MAX_EXPORT_TEXT_BYTES", len(SKILL_MD) + 10)
        world.custom_skill("local::a1", "big", {"SKILL.md": SKILL_MD, "a.md": b"x" * 11, "b.md": b"y" * 5}, directory="big")
        world.expert("lead", "Lead", skills=("local::a1",))

        plan = await build_export_plan("lead")

        assert sorted(plan.skills[0].files) == ["SKILL.md", "b.md"]
        assert _reasons(plan, "skill_file") == {"big/a.md": Omit.TOTAL_SIZE_EXCEEDED}

    @pytest.mark.asyncio
    async def test_package_directory_names_are_valid_and_unique(self, world: ExportWorld) -> None:
        world.custom_skill("local::a1", "My Skill", directory="My Skill")  # folder name is not a valid package name
        world.custom_skill("local::b2", "dup", directory="dup")
        world.custom_skill("local::c3", "dup", directory="dup")
        world.expert("lead", "Lead", skills=("local::a1", "local::b2", "local::c3"))

        plan = await build_export_plan("lead")

        names = [skill.package_name for skill in plan.skills]
        assert names[0] == "my-skill"
        assert names[1:] == ["dup", "dup-2"]


class TestConnectors:
    @pytest.mark.asyncio
    async def test_shared_connectors_are_declarations_and_the_rest_is_reported(self, world: ExportWorld) -> None:
        world.server(
            name="docs", type="streamable_http", url="https://docs.example.com/mcp", headers={"Authorization": "Bearer x"}
        )
        world.server(name="local-db", type="stdio", command="/opt/db/server", args=[])
        world.expert("lead", "Lead", mcps=("docs", "local-db", "ghost"))

        plan = await build_export_plan("lead")

        assert [server.name for server in plan.connectors] == ["docs"]
        assert plan.entry.mcp_names == ("docs",)
        assert _reasons(plan, "connector") == {"local-db": Omit.CONNECTOR_LOCAL_PATH, "ghost": Omit.CONNECTOR_MISSING}

    @pytest.mark.asyncio
    async def test_tool_whitelists_only_follow_connectors_that_ship(self, world: ExportWorld) -> None:
        world.server(name="docs", type="streamable_http", url="https://docs.example.com/mcp")
        world.server(name="local-db", type="stdio", command="/opt/db/server")
        world.expert(
            "lead",
            "Lead",
            mcps=("docs", "local-db"),
            metadata={"mcp_tool_selections": {"docs": ["search"], "local-db": ["query"]}},
        )

        plan = await build_export_plan("lead")

        assert plan.entry.metadata["mcp_tool_selections"] == {"docs": ["search"]}

    @pytest.mark.asyncio
    async def test_a_connector_used_by_several_experts_is_reported_once(self, world: ExportWorld) -> None:
        world.expert("lead", "Lead", mcps=("ghost",), subagents=("worker",))
        world.expert("worker", "Worker", mcps=("ghost",))

        plan = await build_export_plan("lead")

        assert [(item.name, item.owner) for item in plan.omitted] == [("ghost", "Lead")]


class TestWorkspaceAndSettings:
    @pytest.mark.asyncio
    async def test_templates_of_the_entry_expert_ship_and_unreviewable_ones_are_reported(self, world: ExportWorld) -> None:
        encoded = encode_template_files({"README.md": b"hello", "data/seed.csv": b"a,b\n", "logo.png": b"\x89PNG\x00\x01"})
        world.expert("lead", "Lead", metadata={"engine_params": {TEMPLATE_FILES_KEY: encoded.files}})

        plan = await build_export_plan("lead")

        assert plan.workspace_files == {"README.md": b"hello", "data/seed.csv": b"a,b\n"}
        assert _reasons(plan, "workspace_file") == {"logo.png": Omit.BINARY_FILE}

    @pytest.mark.asyncio
    async def test_sub_expert_templates_are_reported_because_they_ship_with_the_entry_only(self, world: ExportWorld) -> None:
        encoded = encode_template_files({"README.md": b"hello"})
        world.expert("lead", "Lead", subagents=("worker",))
        world.expert("worker", "Worker", metadata={"engine_params": {TEMPLATE_FILES_KEY: encoded.files}})

        plan = await build_export_plan("lead")

        assert plan.workspace_files == {}
        assert ("setting", "workspace_templates", Omit.SUB_EXPERT_WORKSPACE) in _omitted(plan)

    @pytest.mark.asyncio
    async def test_settings_that_do_not_travel_are_named(self, world: ExportWorld) -> None:
        world.expert(
            "lead",
            "Lead",
            max_iterations=400,
            metadata={"openapi_services": [{"name": "crm"}], "tool_gateway_config": {"url": "https://gw"}},
        )

        plan = await build_export_plan("lead")

        assert plan.entry.max_iterations is None
        assert _reasons(plan, "setting") == {
            "openapi_services": Omit.MAY_CARRY_CREDENTIALS,
            "tool_gateway_config": Omit.MAY_CARRY_CREDENTIALS,
            "max_iterations": Omit.ABOVE_DEFAULT,
        }

    @pytest.mark.asyncio
    async def test_the_authors_model_is_a_hint_only(self, world: ExportWorld) -> None:
        world.expert("lead", "Lead", model="gpt-4o")

        plan = await build_export_plan("lead")

        assert plan.entry.metadata["recommended_model"] == "gpt-4o"


def test_omitted_items_are_plain_values() -> None:
    assert OmittedItem("skill", "x", Omit.SKILL_UNAVAILABLE) == OmittedItem("skill", "x", Omit.SKILL_UNAVAILABLE, None)
