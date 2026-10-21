"""Expert persistence of plugin imports: bindings, same-name policies, rollback."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from myrm_agent_harness.agent.plugins.models import PluginAgent, PluginParseResult
from myrm_agent_harness.agent.plugins.rules import MAX_TEMPLATE_FILE_BYTES

from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.agent_service import AgentService
from app.services.plugins._agent_persist import AgentImportOutcome, _drop_invalid, persist_imported_agents
from app.services.plugins._agent_plan import AgentPlan
from app.services.plugins._models import PluginConfirmItem, PluginImportSession
from app.services.plugins._preview_context import ExistingExpert, PreviewContext
from app.services.plugins.agent_surface import import_agent_fields
from app.services.plugins.template_workspace import TEMPLATE_FILES_KEY


class FakeAgents:
    """In-memory stand-in for the AgentService calls the import makes."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.created: list[AgentCreate] = []
        self.updated: list[tuple[str, AgentUpdate]] = []
        self.deleted: list[str] = []
        self.existing_names: set[str] = set()
        self.profiles: dict[str, SimpleNamespace] = {}
        self.fail_create_for: str | None = None
        self.fail_update = False
        self.snapshot_saved = True

        async def create_agent(data: AgentCreate) -> SimpleNamespace:
            if data.name == self.fail_create_for:
                raise RuntimeError("database is locked")
            agent_id = f"new-{len(self.created) + 1}"
            self.created.append(data)
            return SimpleNamespace(id=agent_id, display_name=data.name)

        async def update_agent(agent_id: str, data: AgentUpdate) -> SimpleNamespace:
            if self.fail_update:
                raise RuntimeError("database is locked")
            self.updated.append((agent_id, data))
            return SimpleNamespace(profile=None, snapshot_saved=self.snapshot_saved)

        async def delete_agent(agent_id: str) -> bool:
            self.deleted.append(agent_id)
            return True

        async def get_agent_by_id(agent_id: str) -> SimpleNamespace | None:
            return self.profiles.get(agent_id)

        async def get_agents_by_name(name: str) -> list[SimpleNamespace]:
            return [SimpleNamespace(id="dup")] if name.casefold() in self.existing_names else []

        for attr, fn in (
            ("create_agent", create_agent),
            ("update_agent", update_agent),
            ("delete_agent", delete_agent),
            ("get_agent_by_id", get_agent_by_id),
            ("get_agents_by_name", get_agents_by_name),
        ):
            monkeypatch.setattr(AgentService, attr, staticmethod(fn))


def _session(agents: list[PluginAgent], workspace: dict[str, bytes] | None = None) -> PluginImportSession:
    return PluginImportSession(
        plugin_result=PluginParseResult(agents=agents, workspace_files=workspace or {}),
        agents_by_key={f"agent:{i}": agent for i, agent in enumerate(agents)},
    )


def _install(session: PluginImportSession, resolution: str = "install") -> list[PluginConfirmItem]:
    return [PluginConfirmItem("agent", vid, resolution, agent.name) for vid, agent in session.agents_by_key.items()]


async def _persist(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
    *,
    context: PreviewContext | None = None,
    skills: dict[str, str] | None = None,
    servers: list[str] | None = None,
) -> AgentImportOutcome:
    return await persist_imported_agents(
        session,
        decisions,
        context=context or PreviewContext(),
        imported_skill_ids=skills or {},
        imported_servers=servers or [],
    )


LEAD = PluginAgent(
    name="Lead Analyst",
    description="Coordinates",
    system_prompt="Coordinate.",
    max_iterations=300,
    tool_names=("web_search", "browser"),
    subagent_names=("Data Scraper",),
    is_entry_agent=True,
)
SCRAPER = PluginAgent(name="Data Scraper", system_prompt="Scrape.", is_subagent=True)


class TestCreate:
    async def test_sub_expert_is_created_first_and_linked_with_team_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        session = _session([LEAD, SCRAPER], {"starter.txt": b"hello"})

        outcome = await _persist(session, _install(session), skills={"summarize": "local::s1"}, servers=["fetch"])

        assert [c.name for c in fake.created] == ["Data Scraper", "Lead Analyst"]
        sub, lead = fake.created
        assert lead.subagent_ids == ["new-1"] and lead.agent_type == "team"
        assert sub.subagent_ids == [] and sub.agent_type == "individual"
        # the entry expert carries the package's skills/connectors; the sub-expert only what it declares
        assert lead.skill_ids == ["local::s1"] and lead.mcp_ids == ["fetch"]
        assert sub.skill_ids == [] and sub.mcp_ids == []
        # templates belong to the entry expert only
        assert lead.engine_params == {TEMPLATE_FILES_KEY: {"starter.txt": "hello"}}
        assert sub.engine_params is None
        assert outcome.agent_ids == ["new-1", "new-2"]
        assert outcome.failures == ()

    async def test_tighten_only_limits_are_applied_and_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        session = _session([LEAD, SCRAPER])

        outcome = await _persist(session, _install(session))

        lead = fake.created[1]
        assert lead.max_iterations == 50
        assert lead.enabled_builtin_tools == ["web_search"]
        entry = next(e for e in outcome.entries if e.package_name == "Lead Analyst")
        assert entry.withheld_tools == ("browser",)

    async def test_oversized_template_files_are_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        session = _session(
            [PluginAgent(name="Solo", is_entry_agent=True)], {"big.bin": b"x" * (MAX_TEMPLATE_FILE_BYTES + 1), "ok.txt": b"ok"}
        )

        await _persist(session, _install(session))

        assert fake.created[0].engine_params == {TEMPLATE_FILES_KEY: {"ok.txt": "ok"}}

    async def test_agents_without_a_decision_or_skipped_are_not_imported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        session = _session([LEAD, SCRAPER])

        outcome = await _persist(session, [PluginConfirmItem("agent", "agent:1", "skip", "Data Scraper")])

        assert fake.created == []
        assert outcome.skipped == 2

    async def test_unresolved_references_are_reported_not_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        FakeAgents(monkeypatch)
        agent = PluginAgent(name="Solo", skill_names=("ghost",), mcp_names=("nope",), is_entry_agent=True)
        session = _session([agent])

        outcome = await _persist(session, _install(session))

        entry = outcome.entries[0]
        assert entry.unresolved_skills == ("ghost",) and entry.unresolved_connectors == ("nope",)

    async def test_declared_references_resolve_against_installed_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        agent = PluginAgent(name="Solo", skill_names=("web-research",), mcp_names=("db",), is_entry_agent=True)
        session = _session([agent])
        context = PreviewContext(skill_ids_by_name={"web-research": "web-research"}, server_names=frozenset({"db"}))

        await _persist(session, _install(session), context=context)

        assert fake.created[0].skill_ids == ["web-research"] and fake.created[0].mcp_ids == ["db"]


class TestSameNamePolicies:
    CONTEXT = PreviewContext(experts_by_name={"lead analyst": ExistingExpert("old-lead", is_built_in=False)})

    async def test_install_creates_a_renamed_copy_and_never_touches_the_existing_expert(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeAgents(monkeypatch)
        fake.existing_names = {"lead analyst (imported)"}
        session = _session([PluginAgent(name="Lead Analyst", is_entry_agent=True)])

        outcome = await _persist(session, _install(session), context=self.CONTEXT)

        assert fake.created[0].name == "Lead Analyst (imported 2)"
        assert fake.updated == []
        assert outcome.entries[0].action == "created" and outcome.entries[0].stored_name == "Lead Analyst (imported 2)"

    async def test_replace_updates_the_users_expert_in_place_after_creations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        fake.profiles["old-lead"] = SimpleNamespace(metadata={"engine_params": {"keep": 1}})
        session = _session([LEAD, SCRAPER], {"starter.txt": b"hello"})
        decisions = [
            PluginConfirmItem("agent", "agent:0", "replace", "Lead Analyst"),
            PluginConfirmItem("agent", "agent:1", "install", "Data Scraper"),
        ]

        outcome = await _persist(session, decisions, context=self.CONTEXT)

        assert [c.name for c in fake.created] == ["Data Scraper"]
        agent_id, update = fake.updated[0]
        assert agent_id == "old-lead"
        assert "name" not in update.model_fields_set  # identity stays
        assert update.subagent_ids == ["new-1"] and update.agent_type == "team"
        assert update.engine_params == {"keep": 1, TEMPLATE_FILES_KEY: {"starter.txt": "hello"}}
        replaced = next(e for e in outcome.entries if e.action == "replaced")
        assert replaced.previous_version_saved is True

    async def test_replace_reports_when_no_snapshot_could_be_saved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        fake.snapshot_saved = False
        session = _session([PluginAgent(name="Lead Analyst", is_entry_agent=True)])

        outcome = await _persist(session, _install(session, "replace"), context=self.CONTEXT)

        assert outcome.entries[0].previous_version_saved is False

    async def test_built_in_experts_are_never_replaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        context = PreviewContext(experts_by_name={"lead analyst": ExistingExpert("builtin-1", is_built_in=True)})
        session = _session([PluginAgent(name="Lead Analyst", is_entry_agent=True)])

        outcome = await _persist(session, _install(session, "replace"), context=context)

        assert fake.updated == []
        assert fake.created[0].name == "Lead Analyst (imported)"
        assert outcome.entries[0].action == "created"


class TestFailureHandling:
    async def test_a_failing_write_rolls_back_every_expert_created_by_the_import(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeAgents(monkeypatch)
        fake.fail_create_for = "Lead Analyst"
        session = _session([LEAD, SCRAPER])

        outcome = await _persist(session, _install(session))

        assert fake.deleted == ["new-1"]  # the sub-expert created before the failure
        assert outcome.entries == ()
        assert {f.name for f in outcome.failures} == {"Lead Analyst", "Data Scraper"}
        assert all(f.code == "persist_failed" for f in outcome.failures)

    async def test_failed_replacement_keeps_already_applied_replacements_and_rolls_back_creations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeAgents(monkeypatch)
        fake.fail_update = True
        context = PreviewContext(experts_by_name={"lead analyst": ExistingExpert("old-lead", is_built_in=False)})
        session = _session([LEAD, SCRAPER])
        decisions = [
            PluginConfirmItem("agent", "agent:0", "replace", "Lead Analyst"),
            PluginConfirmItem("agent", "agent:1", "install", "Data Scraper"),
        ]

        outcome = await _persist(session, decisions, context=context)

        assert fake.deleted == ["new-1"]
        assert outcome.entries == ()
        assert {f.name for f in outcome.failures} == {"Lead Analyst", "Data Scraper"}

    def test_invalid_expert_is_reported_and_unlinked_from_its_lead(self) -> None:
        invalid = PluginAgent(name="Broken")
        plan_invalid = AgentPlan("agent:1", invalid, import_agent_fields(invalid), is_entry=False)
        plan_invalid.imported.fields["max_iterations"] = 1  # below AgentBase's lower bound
        lead = PluginAgent(name="Lead", is_entry_agent=True)
        plan_lead = AgentPlan("agent:0", lead, import_agent_fields(lead), is_entry=True, sub_keys=["agent:1"])

        remaining, failures = _drop_invalid([plan_invalid, plan_lead], {})

        assert remaining == [plan_lead]
        assert plan_lead.sub_keys == [] and plan_lead.unresolved_subagents == ["Broken"]
        assert [(f.name, f.code) for f in failures] == [("Broken", "invalid_agent")]
