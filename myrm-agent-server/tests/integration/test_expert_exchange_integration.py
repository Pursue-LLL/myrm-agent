"""Integration: experts cross two installations through the real stack.

The acceptance suites in ``tests/services/plugins`` run against a fake installation. This module
runs the same exchange on real components - AgentService on the database, the persisted connector
store, the skill store and its install pipeline, the export and import routes and the ZIP parser -
with nothing mocked on the path: export on one installation, an empty second installation, import.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Literal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.backends.profiles.types import AgentProfile
from sqlalchemy import delete

from app.api.plugins import export_router, import_router
from app.api.plugins.export import ExportPreviewResponse
from app.api.plugins.import_ import (
    PluginConfirmComponent,
    PluginImportConfirmRequest,
    PluginImportConfirmResponse,
    PluginImportPreviewResponse,
)
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.skills.marketplace.market_service import market_service
from app.core.skills.models import Skill
from app.core.skills.packaging.collect import collect_skill_files
from app.core.skills.store.service import skills_service
from app.database.connection import get_session_factory
from app.database.dto import AgentCreate
from app.database.models import UserConfig
from app.services.agent.agent_service import AgentService
from app.services.config.service import config_service

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
PROMPT_CANARY = "sk-ant-api03-IntegrationPromptCanary0123456789"
HEADER_CANARY = "live-docs-token-4f9a1c"
LEAK_PATH = "/Users/alice/research/notes"

Resolution = Literal["install", "replace", "skip"]


@pytest.fixture(autouse=True)
def _skill_state_manager(tmp_path: Path) -> Iterator[None]:
    """Mirror app startup: ``create_agent`` and skill enabling read the global SkillStateManager."""
    import app.core.skills.state_manager_instance as smi

    previous = smi._state_manager
    smi.init_state_manager(base_dir=str(tmp_path / "skill-state"))
    yield
    smi._state_manager = previous


async def _forget_connectors() -> None:
    async with get_session_factory()() as session:
        await session.execute(delete(UserConfig).where(UserConfig.config_key == "mcpServers"))
        await session.commit()
    invalidate_user_configs_cache()


@pytest.fixture(autouse=True)
async def created_agents() -> AsyncIterator[list[str]]:
    """Ids of experts to remove afterwards; the connector store starts and ends empty."""
    await _forget_connectors()
    ids: list[str] = []
    yield ids
    for agent_id in reversed(ids):
        await AgentService.delete_agent(agent_id)
    await _forget_connectors()


@pytest.fixture(autouse=True)
async def installed_skills() -> AsyncIterator[list[str]]:
    """Ids of skills installed by a test; they are uninstalled afterwards."""
    ids: list[str] = []
    yield ids
    for skill_id in ids:
        await market_service.uninstall(skill_id)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(import_router, prefix="/api/plugins")
    app.include_router(export_router, prefix="/api/plugins")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def _archive(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _note_kit() -> bytes:
    """The plugin through which the first installation obtains its ``notes`` skill."""
    manifest = {"$schema": PLUGIN_SCHEMA, "name": "note-kit", "version": "1.0.0", "description": "Tidy research notes"}
    return _archive(
        {
            "plugin.json": json.dumps(manifest),
            "skills/notes/SKILL.md": "---\nname: notes\ndescription: Keeps research notes tidy\n---\n\n# Notes\n\nFile every finding.\n",
            "skills/notes/references/layout.md": f"Notes live in {LEAK_PATH} on this machine.\n",
        }
    )


async def _seed_team(created_agents: list[str]) -> tuple[str, str]:
    """A Lead with a leaked key, an escalating policy and a remote connector, plus its Researcher."""
    await config_service.set(
        "mcpServers",
        {
            "mcpConfigs": [
                {
                    "name": "docs",
                    "type": "streamable_http",
                    "url": "https://docs.example.com/mcp",
                    "headers": {"Authorization": f"Bearer {HEADER_CANARY}"},
                    "enabled": True,
                }
            ]
        },
        device_id="integration-test",
    )
    invalidate_user_configs_cache()
    researcher = await AgentService.create_agent(
        AgentCreate(name="Researcher", description="Digs for sources", system_prompt="You research.")
    )
    lead = await AgentService.create_agent(
        AgentCreate(
            name="Lead",
            description="Plans the work",
            system_prompt=f"Call the API with {PROMPT_CANARY} when asked.\nBe brief.",
            mcp_ids=["docs"],
            subagent_ids=[researcher.id],
            agent_type="team",
            security_overrides={"yolo_mode_enabled": True},
            trusted_desktop_apps=[{"name": "SAP GUI"}],
        )
    )
    created_agents.extend([researcher.id, lead.id])
    return lead.id, researcher.id


async def _preview_export(client: AsyncClient, agent_id: str) -> ExportPreviewResponse:
    response = await client.post("/api/plugins/export/preview", json={"agent_id": agent_id})
    assert response.status_code == 200, response.text
    return ExportPreviewResponse.model_validate(response.json())


async def _download(client: AsyncClient, agent_id: str, preview: ExportPreviewResponse) -> bytes:
    """Redact every finding, as the review dialog's default does."""
    response = await client.post(
        "/api/plugins/export",
        json={"agent_id": agent_id, "apply_redactions": True, "review_digest": preview.review_digest},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    return response.content


async def _export_team(client: AsyncClient, lead_id: str) -> bytes:
    preview = await _preview_export(client, lead_id)
    assert [expert.name for expert in preview.experts] == ["Lead", "Researcher"]
    assert [connector.name for connector in preview.connectors] == ["docs"]
    assert preview.omitted == []
    assert preview.redactions, "the leaked key must surface as a finding"
    return await _download(client, lead_id, preview)


async def _preview_import(client: AsyncClient, package: bytes) -> PluginImportPreviewResponse:
    response = await client.post("/api/plugins/import/preview", files={"file": ("package.zip", package, "application/zip")})
    assert response.status_code == 200, response.text
    return PluginImportPreviewResponse.model_validate(response.json())


async def _confirm(
    client: AsyncClient,
    preview: PluginImportPreviewResponse,
    *,
    agents: Resolution,
    servers: Resolution = "install",
    skills: Resolution = "install",
) -> PluginImportConfirmResponse:
    request = PluginImportConfirmRequest(
        session_id=preview.session_id,
        skills=[
            PluginConfirmComponent(component="skill", virtual_id=skill.virtual_id, name=skill.name, resolution=skills)
            for skill in preview.skills
        ],
        servers=[
            PluginConfirmComponent(component="mcp", virtual_id=server.virtual_id, name=server.name, resolution=servers)
            for server in preview.servers
        ],
        agents=[
            PluginConfirmComponent(component="agent", virtual_id=agent.virtual_id, name=agent.name, resolution=agents)
            for agent in preview.agents
        ],
    )
    response = await client.post("/api/plugins/import/confirm", json=request.model_dump())
    assert response.status_code == 200, response.text
    return PluginImportConfirmResponse.model_validate(response.json())


async def _one(name: str) -> AgentProfile:
    found = await AgentService.get_agents_by_name(name)
    assert len(found) == 1, f"{name!r}: {len(found)} experts"
    return found[0]


async def _notes_skill() -> Skill:
    found = [skill for skill in await skills_service.list_skills() if skill.name == "notes"]
    assert len(found) == 1, f"'notes': {len(found)} skills"
    return found[0]


class TestAcrossTwoInstallations:
    @pytest.mark.asyncio
    async def test_a_team_lands_intact_on_an_empty_installation(self, client: AsyncClient, created_agents: list[str]) -> None:
        lead_id, _ = await _seed_team(created_agents)
        package = await _export_team(client, lead_id)

        archive = zipfile.ZipFile(io.BytesIO(package))
        contents = b"\n".join(archive.read(name) for name in archive.namelist()).lower()
        for secret in (PROMPT_CANARY, HEADER_CANARY, "yolo", "sap gui"):
            assert secret.lower().encode() not in contents, f"{secret!r} left the machine"

        # The second installation: nothing of the first one exists there.
        for agent_id in reversed(created_agents):
            await AgentService.delete_agent(agent_id)
        created_agents.clear()
        await _forget_connectors()

        preview = await _preview_import(client, package)
        assert [agent.name for agent in preview.agents] == ["Lead", "Researcher"]
        assert not any(agent.conflict for agent in preview.agents)
        assert [server.name for server in preview.servers] == ["docs"]

        result = await _confirm(client, preview, agents="install")
        assert result.failures == []
        assert (result.imported_agents, result.imported_servers) == (2, 1)
        assert result.required_secret_keys == ["Authorization"]
        created_agents.extend(result.created_agent_ids)

        lead, researcher = await _one("Lead"), await _one("Researcher")
        assert (lead.metadata or {})["subagent_ids"] == [researcher.id]  # wired to the new Researcher, not a stale id
        assert (lead.metadata or {})["mcp_ids"] == ["docs"]
        assert "Be brief." in (lead.system_prompt or "")
        assert PROMPT_CANARY not in (lead.system_prompt or "")
        for imported in (lead, researcher):
            meta = imported.metadata or {}
            assert not meta.get("security_overrides")
            assert not meta.get("trusted_desktop_apps")

        record = await config_service.get("mcpServers")
        assert record is not None and isinstance(record.value, dict)
        [docs] = [cfg for cfg in record.value["mcpConfigs"] if cfg["name"] == "docs"]
        assert docs["enabled"] is False  # a package never switches a connector on
        assert docs["headers"] == {"Authorization": "{{secret:Authorization}}"}

    @pytest.mark.asyncio
    async def test_a_custom_skill_travels_with_its_expert(
        self, client: AsyncClient, created_agents: list[str], installed_skills: list[str]
    ) -> None:
        obtained = await _confirm(client, await _preview_import(client, _note_kit()), agents="install")
        assert obtained.failures == [] and obtained.imported_skills == 1
        skill = await _notes_skill()
        installed_skills.append(skill.id)
        scribe = await AgentService.create_agent(
            AgentCreate(name="Scribe", description="Files notes", system_prompt="You keep notes.", skill_ids=[skill.id])
        )
        created_agents.append(scribe.id)

        preview = await _preview_export(client, scribe.id)
        assert [(item.name, item.source, item.file_count) for item in preview.skills] == [("notes", "custom", 2)]
        assert any(LEAK_PATH in found.original for findings in (preview.redactions or {}).values() for found in findings)
        package = await _download(client, scribe.id, preview)

        archive = zipfile.ZipFile(io.BytesIO(package))
        shipped = [archive.read(name) for name in archive.namelist() if "/skills/notes/" in name]
        assert len(shipped) == 2 and not any(LEAK_PATH.encode() in content for content in shipped)

        # The second installation has neither the expert nor the skill.
        await AgentService.delete_agent(scribe.id)
        created_agents.remove(scribe.id)
        assert (await market_service.uninstall(skill.id)).success
        installed_skills.remove(skill.id)

        arriving = await _preview_import(client, package)
        assert [(item.name, item.conflict) for item in arriving.skills] == [("notes", False)]
        result = await _confirm(client, arriving, agents="install")
        assert result.failures == [] and result.imported_skills == 1
        created_agents.extend(result.created_agent_ids)
        reinstalled = await _notes_skill()
        installed_skills.append(reinstalled.id)

        assert (await _one("Scribe")).skills == [reinstalled.id]  # the expert points at the skill installed here
        files = await collect_skill_files(skills_service, reinstalled.id)
        assert b"File every finding." in files["SKILL.md"]
        assert LEAK_PATH.encode() not in files["references/layout.md"]

    @pytest.mark.asyncio
    async def test_the_same_installation_keeps_its_originals_until_asked_to_replace(
        self, client: AsyncClient, created_agents: list[str]
    ) -> None:
        lead_id, researcher_id = await _seed_team(created_agents)
        package = await _export_team(client, lead_id)

        preview = await _preview_import(client, package)
        assert all(agent.conflict for agent in preview.agents)

        copies = await _confirm(client, preview, agents="install", servers="skip")
        created_agents.extend(copies.created_agent_ids)
        assert sorted(entry.stored_name for entry in copies.agents) == ["Lead (imported)", "Researcher (imported)"]
        lead_copy, researcher_copy = await _one("Lead (imported)"), await _one("Researcher (imported)")
        assert (lead_copy.metadata or {})["subagent_ids"] == [researcher_copy.id]
        original = await AgentService.get_agent_by_id(lead_id)
        assert original is not None and PROMPT_CANARY in (original.system_prompt or "")  # the user's own expert is untouched
        assert (original.metadata or {})["subagent_ids"] == [researcher_id]

        replaced = await _confirm(client, await _preview_import(client, package), agents="replace", servers="skip")
        assert {entry.action for entry in replaced.agents} == {"replaced"}
        assert all(entry.previous_version_saved for entry in replaced.agents)
        assert set(replaced.created_agent_ids) == {lead_id, researcher_id}
        updated = await AgentService.get_agent_by_id(lead_id)
        assert updated is not None and PROMPT_CANARY not in (updated.system_prompt or "")
        # A package neither sets nor erases the user's own security policy on an expert it replaces.
        assert (updated.metadata or {}).get("security_overrides") == {"yolo_mode_enabled": True}
