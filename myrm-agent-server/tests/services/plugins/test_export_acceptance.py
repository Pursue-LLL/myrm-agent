"""Acceptance of the expert export against anchors outside the code that wrote it.

The unit suites prove each piece. These tests hold the finished package to what a stranger
(or the other half of the product) would check:

- the frozen official Agent Plugins schemas and archive-path hygiene,
- redaction that replaces secrets and changes nothing else,
- an omitted list that accounts for everything an expert declared,
- export -> import -> export settling on a fixed point (both halves of one table cannot drift),
- a package made on a local installation landing in a cloud deployment.
"""

from __future__ import annotations

import io
import json
import re
import stat
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

import jsonschema
import pytest
from myrm_agent_harness.agent.plugins.models import PluginParseResult
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.services.plugins._agent_persist import _build_create
from app.services.plugins._agent_plan import plan_agents
from app.services.plugins._mcp_persist import _server_to_config_dict
from app.services.plugins._preview import build_preview_result
from app.services.plugins._preview_context import PreviewContext
from app.services.plugins.export_service import ExportedPackage, OmittedItem, export_expert, preview_expert_export
from app.services.plugins.import_service import parse_plugin_zip
from app.services.plugins.template_workspace import TEMPLATE_FILES_KEY, decode_template_files, encode_template_files
from tests.support.export_world import SKILL_MD, ExportWorld

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agent_plugins"

SKILL_CANARY = "ghp_AcceptanceSkillCanary0123456789"
PROMPT_CANARY = "sk-ant-api03-AcceptancePromptCanary0123456789"


def _schema(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text())


async def _export(agent_id: str = "lead") -> ExportedPackage:
    return await export_expert(agent_id, apply_redactions=True, ignored_redactions=None, review_digest=None)


def _entries(package: ExportedPackage) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(package.zip_content)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}


@pytest.fixture
def team(world: ExportWorld) -> ExportWorld:
    """A team whose every dependency is portable and already within the limits an import keeps."""
    world.custom_skill(
        "local::a1",
        "notes",
        {"SKILL.md": SKILL_MD, "scripts/run.sh": b"#!/bin/sh\necho notes\n", "notes.txt": b"notes\n"},
        directory="notes",
    )
    world.preset_skill("web-research", "web-research")
    world.server(
        name="docs", type="streamable_http", url="https://docs.example.com/mcp", headers={"Authorization": "Bearer live"}
    )
    world.server(
        name="search", type="stdio", command="npx", args=["-y", "@acme/search-mcp"], extra_params={"env": {"ACME_KEY": "k"}}
    )
    templates = encode_template_files({"README.md": b"# Team notes\n"})
    world.expert(
        "lead",
        "Lead",
        skills=("local::a1", "web-research"),
        mcps=("docs", "search"),
        subagents=("worker",),
        metadata={
            "personality_style": "professional",
            "suggestion_prompts": ["Summarize the notes"],
            "mcp_tool_selections": {"docs": ["search_docs"]},
            "engine_params": {TEMPLATE_FILES_KEY: templates.files},
        },
    )
    world.expert("worker", "Worker", skills=("local::a1",), metadata={"personality_style": "professional"})
    return world


class TestOfficialStandard:
    @pytest.mark.asyncio
    async def test_manifest_and_connectors_validate_against_the_frozen_schemas(self, team: ExportWorld) -> None:
        entries = _entries(await _export())
        manifest = json.loads(entries["lead/plugin.json"])
        plugin_schema = _schema("plugin.schema.json")

        jsonschema.validate(manifest, plugin_schema)
        jsonschema.validate(json.loads(entries["lead/mcp.json"]), _schema("mcp.schema.json"))
        # Everything Myrm adds lives under its own extension namespace, never as a top-level field.
        assert set(manifest) <= set(plugin_schema["properties"])  # type: ignore[arg-type]
        assert set(manifest["extensions"]) == {"ai.myrm"}

    @pytest.mark.asyncio
    async def test_archive_paths_stay_inside_one_wrapper_directory(self, team: ExportWorld) -> None:
        package = await _export()
        with zipfile.ZipFile(io.BytesIO(package.zip_content)) as archive:
            infos = archive.infolist()

        names = [info.filename for info in infos]
        assert len(names) == len(set(names))
        assert {name.split("/", 1)[0] for name in names} == {"lead"}
        for info in infos:
            path = PurePosixPath(info.filename)
            assert not path.is_absolute(), info.filename
            assert ".." not in path.parts and "\\" not in info.filename, info.filename
            mode = info.external_attr >> 16
            assert not stat.S_ISLNK(mode), f"{info.filename} is a symbolic link"
            assert mode == 0 or stat.S_ISREG(mode) or stat.S_ISDIR(mode), f"{info.filename} is not a regular file"


@pytest.fixture
def leaky_team(team: ExportWorld) -> ExportWorld:
    team.skill_files["local::a1"]["scripts/run.sh"] = f"#!/bin/sh\nexport GITHUB_TOKEN={SKILL_CANARY}\necho notes\n".encode()
    team.profiles["lead"].system_prompt = f"Call the API with {PROMPT_CANARY} when asked.\nBe brief."
    return team


def _differs_only_at(secrets: Sequence[str], original: bytes, redacted: bytes) -> bool:
    """``redacted`` is ``original`` with each secret swapped for a short placeholder and nothing else touched."""
    pieces = re.split("|".join(re.escape(secret) for secret in secrets), original.decode())
    pattern = ".{1,80}?".join(re.escape(piece) for piece in pieces)
    return re.fullmatch(pattern, redacted.decode(), re.DOTALL) is not None


class TestRedactionTouchesOnlySecrets:
    @pytest.mark.asyncio
    async def test_the_redacted_package_is_the_original_minus_its_secrets(self, leaky_team: ExportWorld) -> None:
        preview = await preview_expert_export("lead")
        keep_everything = {path: list(range(len(found))) for path, found in preview.redactions.items()}
        original = _entries(
            await export_expert(
                "lead", apply_redactions=False, ignored_redactions=keep_everything, review_digest=preview.review_digest
            )
        )
        redacted = _entries(await _export())

        assert original.keys() == redacted.keys()
        assert any(SKILL_CANARY.encode() in content for content in original.values())
        assert not any(secret.encode() in content for content in redacted.values() for secret in (SKILL_CANARY, PROMPT_CANARY))
        changed = sorted(path for path in original if original[path] != redacted[path])
        assert changed == ["lead/ai.myrm/agents/lead.md", "lead/skills/notes/scripts/run.sh"]
        for path in changed:
            assert _differs_only_at((SKILL_CANARY, PROMPT_CANARY), original[path], redacted[path]), path


@pytest.fixture
def obstructed(team: ExportWorld) -> ExportWorld:
    """The team plus one dependency of every kind that cannot travel."""
    team.skill_files["local::a1"].update({"assets/logo.png": b"\x89PNG\0\0", ".env": b"KEY=1\n"})
    team.server(name="tool", type="stdio", command="/opt/tool/bin/tool")
    team.expert("builtin", "Builtin", built_in=True)
    lead = team.profiles["lead"]
    lead.skills.append("local::gone")
    lead.metadata["mcp_ids"] += ["tool", "nope"]
    lead.metadata["subagent_ids"] += ["builtin", "ghost"]
    lead.metadata["openapi_services"] = {"crm": {"token": "x"}}
    lead.max_iterations = 99
    team.profiles["worker"].metadata["subagent_ids"] = ["lead"]
    return team


def _accounting_gaps(world: ExportWorld, package: PluginParseResult, omitted: Sequence[OmittedItem]) -> list[str]:
    """Declared dependencies of the shipped experts that neither ship nor appear in the omitted list (and vice versa)."""
    reported = {(item.kind, item.owner, item.name) for item in omitted}
    agents = {agent.name: agent for agent in package.agents}
    gaps: list[str] = []

    for profile in world.profiles.values():
        agent = agents.get(profile.display_name)
        if agent is None:
            continue  # an expert that did not ship is accounted for by the link that pointed at it
        owner = profile.display_name
        for ref in profile.skills:
            skill = world.skills.get(ref)
            shipped = (
                skill is not None
                and (skill.name if skill.type == SkillType.PREBUILT else Path(skill.storage_path).name) in agent.skill_names
            )
            listed = ("skill", owner, ref if skill is None else skill.name) in reported
            gaps += _verdict(f"{owner} skill {ref}", shipped, listed)
        for name in profile.metadata["mcp_ids"]:
            gaps += _verdict(f"{owner} connector {name}", name in agent.mcp_names, ("connector", owner, name) in reported)
        for child_id in profile.metadata["subagent_ids"]:
            child = world.profiles.get(child_id)
            shipped = child is not None and child.display_name in agent.subagent_names
            labels = {child_id, child.display_name if child else child_id}
            gaps += _verdict(
                f"{owner} sub-expert {child_id}", shipped, any(("expert", owner, label) in reported for label in labels)
            )

    gaps += _file_gaps(world, package, omitted)
    return gaps


def _verdict(what: str, shipped: bool, listed: bool) -> list[str]:
    if shipped == listed:
        return [f"{what}: {'both ships and is listed as left out' if shipped else 'is neither shipped nor listed'}"]
    return []


def _file_gaps(world: ExportWorld, package: PluginParseResult, omitted: Sequence[OmittedItem]) -> list[str]:
    gaps: list[str] = []
    for skill in package.skills:
        source = next(
            files for sid, files in world.skill_files.items() if Path(world.skills[sid].storage_path).name == skill.name
        )
        left_out = {
            item.name.removeprefix(f"{skill.name}/")
            for item in omitted
            if item.kind == "skill_file" and item.name.startswith(f"{skill.name}/")
        }
        if set(source) != set(skill.files) | left_out or set(skill.files) & left_out:
            gaps.append(
                f"files of skill {skill.name}: {sorted(source)} vs shipped {sorted(skill.files)} + left out {sorted(left_out)}"
            )
    templates = decode_template_files(world.profiles["lead"].metadata["engine_params"][TEMPLATE_FILES_KEY])
    left_out_templates = {item.name for item in omitted if item.kind == "workspace_file"}
    if set(templates) != set(package.workspace_files) | left_out_templates:
        gaps.append("workspace templates are not accounted for")
    return gaps


class TestNothingGoesMissing:
    @pytest.mark.asyncio
    async def test_every_declared_dependency_ships_or_is_listed(self, obstructed: ExportWorld) -> None:
        preview = await preview_expert_export("lead")
        shipped = parse_plugin_zip((await _export()).zip_content)

        assert _accounting_gaps(obstructed, shipped, preview.plan.omitted) == []

    @pytest.mark.asyncio
    async def test_the_accounting_notices_a_dependency_that_vanished_silently(self, obstructed: ExportWorld) -> None:
        preview = await preview_expert_export("lead")
        shipped = parse_plugin_zip((await _export()).zip_content)
        forgotten = [item for item in preview.plan.omitted if item.name != "ghost"]

        assert len(forgotten) == len(preview.plan.omitted) - 1
        assert _accounting_gaps(obstructed, shipped, forgotten) == ["Lead sub-expert ghost: is neither shipped nor listed"]


def _reinstall(package: ExportedPackage) -> tuple[ExportWorld, str]:
    """A second installation holding what importing ``package`` creates.

    Planning and field projection are the real import code (``plan_agents`` / ``_build_create``);
    only storage is the fake world. Preset skills are part of every installation.
    """
    parsed = parse_plugin_zip(package.zip_content)
    assert parsed.meta is not None
    world = ExportWorld()
    world.preset_skill("web-research", "web-research")
    skill_ids = {"web-research": "web-research"}
    skill_ids.update({skill.name.lower(): f"local::{skill.name}" for skill in parsed.skills})
    for skill in parsed.skills:
        world.custom_skill(skill_ids[skill.name.lower()], skill.name, dict(skill.files), directory=skill.name)
    connectors = [server.name for server in parsed.servers]
    for server in parsed.servers:
        world.server(**_server_to_config_dict(server, plugin_name=parsed.meta.name))

    plans = plan_agents(
        [(f"agent:{index}", agent) for index, agent in enumerate(parsed.agents)],
        resolve_skill=lambda name: skill_ids.get(name.strip().lower()),
        resolve_connector=lambda name: name if name in connectors else None,
        imported_skill_ids=[skill_ids[skill.name.lower()] for skill in parsed.skills],
        imported_connectors=connectors,
    )
    ids = {plan.virtual_id: f"imported-{index}" for index, plan in enumerate(plans)}
    templates = encode_template_files(parsed.workspace_files).files
    entry_id = ""
    for plan in plans:
        create = _build_create(plan, plan.imported.name, [ids[key] for key in plan.sub_keys], templates)
        profile = world.expert(
            ids[plan.virtual_id],
            create.name,
            skills=tuple(create.skill_ids),
            mcps=tuple(create.mcp_ids),
            subagents=tuple(create.subagent_ids),
            description=create.description,
            system_prompt=create.system_prompt,
            metadata={
                "personality_style": create.personality_style,
                "suggestion_prompts": create.suggestion_prompts,
                "allow_discovery": create.allow_discovery,
                "mcp_tool_selections": create.mcp_tool_selections,
                "engine_params": create.engine_params,
            },
        )
        profile.max_iterations = create.max_iterations
        profile.tools_allowed = create.enabled_builtin_tools
        if plan.is_entry:
            entry_id = profile.id
    return world, entry_id


async def _round(package: ExportedPackage) -> ExportedPackage:
    """Import ``package`` into a fresh installation and export its entry expert again."""
    world, entry_id = _reinstall(package)
    with world.installed():
        return await _export(entry_id)


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_a_package_within_the_import_limits_comes_back_unchanged(self, team: ExportWorld) -> None:
        first = await _export()

        assert _entries(await _round(first)) == _entries(first)

    @pytest.mark.asyncio
    async def test_what_an_import_tightens_is_gone_after_one_round_and_stays_gone(self, team: ExportWorld) -> None:
        lead = team.profiles["lead"]
        lead.model = "gpt-4o"  # shown as a hint, never applied
        lead.max_iterations = 99  # above the system default, never carried
        lead.tools_allowed = ["web_search", "shell_exec"]  # beyond the default grants
        first = await _export()

        second = await _round(first)
        third = await _round(second)

        assert _entries(second) != _entries(first)
        assert _entries(third) == _entries(second)


class TestLocalToCloud:
    @pytest.mark.asyncio
    async def test_only_stdio_connectors_degrade_in_a_cloud_deployment(self, team: ExportWorld) -> None:
        parsed = parse_plugin_zip((await _export()).zip_content)
        known = {"web-research": "web-research"}

        local = build_preview_result(parsed, PreviewContext(skill_ids_by_name=known))
        cloud = build_preview_result(parsed, PreviewContext(skill_ids_by_name=known, allow_stdio=False))

        assert {server["name"]: server["blocked_reason"] for server in local["servers"]} == {"docs": None, "search": None}
        assert {server["name"]: server["blocked_reason"] for server in cloud["servers"]} == {
            "docs": None,
            "search": "stdio_not_allowed",
        }
        assert all(skill["blocked_reason"] is None for skill in cloud["skills"])
        lead = next(agent for agent in cloud["agents"] if agent["name"] == "Lead")
        assert lead["is_entry_agent"] is True
        assert lead["unresolved_skills"] == [] and lead["unresolved_subagents"] == []
