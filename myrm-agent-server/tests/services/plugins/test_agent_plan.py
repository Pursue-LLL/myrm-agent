"""Binding plan of package experts: per-expert resolution, entry fallback, ordering."""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.agent.plugins.models import PluginAgent

from app.services.plugins._agent_plan import AgentPlan, plan_agents

SKILLS = {"pdf": "local::pdf", "web": "web-research"}
CONNECTORS = {"fetch", "db"}


def _plan(
    agents: Sequence[PluginAgent],
    *,
    imported_skills: Sequence[str] = ("local::bundled",),
    imported_connectors: Sequence[str] = ("fetch",),
) -> dict[str, AgentPlan]:
    accepted = [(f"agent:{i}", agent) for i, agent in enumerate(agents)]
    plans = plan_agents(
        accepted,
        resolve_skill=lambda name: SKILLS.get(name.strip().lower()),
        resolve_connector=lambda name: name if name in CONNECTORS else None,
        imported_skill_ids=imported_skills,
        imported_connectors=imported_connectors,
    )
    return {plan.virtual_id: plan for plan in plans}


def _entry(
    *,
    skill_names: tuple[str, ...] = (),
    mcp_names: tuple[str, ...] = (),
    subagent_names: tuple[str, ...] = (),
    metadata: dict[str, object] | None = None,
) -> PluginAgent:
    return PluginAgent(
        name="Lead",
        is_entry_agent=True,
        skill_names=skill_names,
        mcp_names=mcp_names,
        subagent_names=subagent_names,
        metadata=metadata or {},
    )


class TestBindings:
    def test_declared_names_resolve_per_expert(self) -> None:
        plans = _plan([_entry(skill_names=("PDF", "missing"), mcp_names=("db", "nope"))])
        plan = plans["agent:0"]
        assert plan.skill_ids == ["local::pdf"]
        assert plan.unresolved_skills == ["missing"]
        assert plan.mcp_ids == ["db"]
        assert plan.unresolved_connectors == ["nope"]

    def test_entry_expert_without_declarations_gets_everything_the_package_installed(self) -> None:
        plan = _plan([_entry()])["agent:0"]
        assert plan.skill_ids == ["local::bundled"]
        assert plan.mcp_ids == ["fetch"]

    def test_sub_expert_without_declarations_gets_nothing(self) -> None:
        plans = _plan([_entry(), PluginAgent(name="Helper", is_subagent=True)])
        assert plans["agent:1"].skill_ids == []
        assert plans["agent:1"].mcp_ids == []

    def test_entry_declaring_something_does_not_get_the_rest(self) -> None:
        plan = _plan([_entry(skill_names=("web",))])["agent:0"]
        assert plan.skill_ids == ["web-research"]
        assert plan.mcp_ids == ["fetch"]  # connectors were not declared, so the fallback applies to them only

    def test_tool_selections_are_limited_to_bound_connectors(self) -> None:
        agent = _entry(mcp_names=("fetch",), metadata={"mcp_tool_selections": {"fetch": ["get"], "db": ["q"]}})
        assert _plan([agent])["agent:0"].tool_selections == {"fetch": ["get"]}


class TestTeamLinks:
    def test_declared_sub_experts_are_linked_and_created_first(self) -> None:
        agents = [_entry(subagent_names=("Scraper",)), PluginAgent(name="Scraper", is_subagent=True), PluginAgent(name="Idle")]
        plans = plan_agents(
            [(f"agent:{i}", a) for i, a in enumerate(agents)],
            resolve_skill=lambda _n: None,
            resolve_connector=lambda _n: None,
            imported_skill_ids=(),
            imported_connectors=(),
        )
        order = [p.virtual_id for p in plans]
        assert order.index("agent:1") < order.index("agent:0")
        lead = next(p for p in plans if p.virtual_id == "agent:0")
        assert lead.sub_keys == ["agent:1"]  # explicit list: "Idle" is not led by Lead

    def test_entry_without_declared_sub_experts_leads_the_rest_of_the_package(self) -> None:
        plans = _plan([_entry(), PluginAgent(name="A"), PluginAgent(name="B")])
        assert plans["agent:0"].sub_keys == ["agent:1", "agent:2"]

    def test_slug_resolves_sub_expert(self) -> None:
        agents = [_entry(subagent_names=("data-scraper",)), PluginAgent(name="Data Scraper", metadata={"slug": "data-scraper"})]
        assert _plan(agents)["agent:0"].sub_keys == ["agent:1"]

    def test_unknown_and_self_references_are_reported(self) -> None:
        plan = _plan([_entry(subagent_names=("Ghost", "Lead"))])["agent:0"]
        assert plan.sub_keys == []
        assert plan.unresolved_subagents == ["Ghost", "Lead"]

    def test_link_cycles_are_broken_instead_of_looping(self) -> None:
        agents = [
            _entry(subagent_names=("B",)),
            PluginAgent(name="B", subagent_names=("C",)),
            PluginAgent(name="C", subagent_names=("B",)),  # closes B -> C -> B
        ]
        plans = plan_agents(
            [(f"agent:{i}", a) for i, a in enumerate(agents)],
            resolve_skill=lambda _n: None,
            resolve_connector=lambda _n: None,
            imported_skill_ids=(),
            imported_connectors=(),
        )
        by_id = {p.virtual_id: p for p in plans}
        assert by_id["agent:1"].sub_keys == ["agent:2"]
        assert by_id["agent:2"].sub_keys == []
        assert [p.virtual_id for p in plans] == ["agent:2", "agent:1", "agent:0"]
