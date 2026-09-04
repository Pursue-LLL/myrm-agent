"""Tests for Agent Plugins agent profiles persistence and workspace template materialization.

Covers:
- PluginAgent persistence with subagent hierarchy linking
- Sanitize imported security overrides (fail-closed against permission escalation)
- Oversized template workspace files defensive guards
- Workspace template files safe materialization with path traversal defense
- HTTP preview & confirm contract with agents and workspace assets
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.plugins.models import (
    AgentPluginManifestMeta,
    PluginAgent,
    PluginParseResult,
)

from app.api.plugins import import_ as import_module
from app.services.plugins._agent_persist import (
    MAX_TEMPLATE_FILE_BYTES,
    materialize_template_workspace_files,
    persist_imported_agents,
    sanitize_imported_security_overrides,
)
from app.services.plugins._models import PluginConfirmItem, PluginImportSession

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


@pytest.fixture(scope="function")
def client() -> TestClient:
    test_app = FastAPI(title="Agent Plugin Import Test App")
    test_app.include_router(import_module.router, prefix="/api/v1/plugins")
    return TestClient(test_app, raise_server_exceptions=False)


class TestAgentPluginPersist:
    """Tests agent profile creation, linking, and security sanitization."""

    def test_sanitize_imported_security_overrides(self) -> None:
        raw_metadata: dict[str, object] = {
            "author": "Alice",
            "version": "1.0",
            "dangerously_skip_permissions": True,
            "bypass_sandbox": True,
            "required_permissions": ["all"],
            "host_execution_allowed": True,
            "custom_tag": "research",
        }
        sanitized = sanitize_imported_security_overrides(raw_metadata)
        assert sanitized == {
            "author": "Alice",
            "version": "1.0",
            "custom_tag": "research",
        }
        assert "dangerously_skip_permissions" not in sanitized
        assert "bypass_sandbox" not in sanitized
        assert "required_permissions" not in sanitized
        assert "host_execution_allowed" not in sanitized

    @pytest.mark.asyncio
    async def test_persist_imported_agents_with_subagent_linking(self) -> None:
        subagent = PluginAgent(
            name="Data Scraper",
            description="Fetches raw web data",
            system_prompt="Scrape data safely.",
            is_subagent=True,
            metadata={"slug": "data_scraper"},
        )
        lead_agent = PluginAgent(
            name="Lead Analyst",
            description="Coordinates research squad",
            system_prompt="Coordinate data analysis.",
            max_iterations=12,
            subagent_names=("Data Scraper",),
            is_entry_agent=True,
        )

        parse_result = PluginParseResult(
            meta=AgentPluginManifestMeta(name="research-team", version="1.0.0"),
            agents=[lead_agent, subagent],
            workspace_files={"starter.txt": b"Starter workspace note"},
        )

        session = PluginImportSession(
            plugin_result=parse_result,
            agents_by_key={
                "agent:0": lead_agent,
                "agent:1": subagent,
            },
        )

        decisions = [
            PluginConfirmItem(
                component="agent",
                virtual_id="agent:0",
                resolution="install",
                name="Lead Analyst",
            ),
            PluginConfirmItem(
                component="agent",
                virtual_id="agent:1",
                resolution="install",
                name="Data Scraper",
            ),
        ]

        created_sub = SimpleNamespace(id="sub-101", name="Data Scraper")
        created_lead = SimpleNamespace(id="lead-202", name="Lead Analyst")

        with patch(
            "app.services.agent.agent_service.AgentService.create_agent",
            side_effect=[created_sub, created_lead],
        ) as mock_create:
            created_ids, skipped = await persist_imported_agents(
                session,
                decisions,
                skill_ids=["skill-search"],
                mcp_names=["fetch-mcp"],
            )

        assert skipped == 0
        assert created_ids == ["sub-101", "lead-202"]
        assert mock_create.call_count == 2

        # Check lead agent subagent_ids binding
        lead_create_arg = mock_create.call_args_list[1][0][0]
        assert lead_create_arg.name == "Lead Analyst"
        assert lead_create_arg.subagent_ids == ["sub-101"]
        assert lead_create_arg.max_iterations == 12
        assert lead_create_arg.skill_ids == ["skill-search"]
        assert lead_create_arg.mcp_ids == ["fetch-mcp"]
        assert lead_create_arg.engine_params == {"template_workspace_files": {"starter.txt": "Starter workspace note"}}

    @pytest.mark.asyncio
    async def test_persist_imported_agents_skips_oversized_workspace_files(self) -> None:
        agent = PluginAgent(name="Solo Agent", is_entry_agent=True)
        parse_result = PluginParseResult(
            agents=[agent],
            workspace_files={
                "oversized.bin": b"x" * (MAX_TEMPLATE_FILE_BYTES + 10),
                "valid.txt": b"ok",
            },
        )
        session = PluginImportSession(
            plugin_result=parse_result,
            agents_by_key={"agent:0": agent},
        )
        decisions = [
            PluginConfirmItem(
                component="agent",
                virtual_id="agent:0",
                resolution="install",
                name="Solo Agent",
            )
        ]

        mock_agent = SimpleNamespace(id="agent-single", name="Solo Agent")
        with patch(
            "app.services.agent.agent_service.AgentService.create_agent",
            return_value=mock_agent,
        ) as mock_create:
            created_ids, _ = await persist_imported_agents(
                session,
                decisions,
                skill_ids=[],
                mcp_names=[],
            )

        assert created_ids == ["agent-single"]
        create_payload = mock_create.call_args[0][0]
        templates = create_payload.engine_params["template_workspace_files"]
        assert "oversized.bin" not in templates
        assert templates["valid.txt"] == "ok"


class TestWorkspaceTemplateMaterialization:
    """Tests safe unpacking and path traversal protection for workspace template files."""

    def test_materialize_valid_text_and_binary_files(self, tmp_path: Path) -> None:
        raw_bytes = b"\x00\x01\x02\x03\xff"
        b64_content = f"base64:{base64.b64encode(raw_bytes).decode('ascii')}"

        template_files: dict[str, object] = {
            "notes/guidelines.md": "# Guidelines\nDo good work.",
            "assets/logo.png": b64_content,
        }

        written = materialize_template_workspace_files(template_files, tmp_path)
        assert len(written) == 2
        assert (tmp_path / "notes/guidelines.md").read_text(encoding="utf-8") == "# Guidelines\nDo good work."
        assert (tmp_path / "assets/logo.png").read_bytes() == raw_bytes

    def test_materialize_blocks_path_traversal(self, tmp_path: Path) -> None:
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir()
        outside_file = tmp_path / "outside.txt"

        malicious_templates: dict[str, object] = {
            "../../outside.txt": "malicious content",
            "subdir/../../../escaped.sh": "#!/bin/sh\nrm -rf /",
            "normal.txt": "safe content",
        }

        written = materialize_template_workspace_files(malicious_templates, sandbox_dir)
        assert written == ["normal.txt"]
        assert not outside_file.exists()
        assert not (tmp_path / "escaped.sh").exists()
        assert (sandbox_dir / "normal.txt").read_text(encoding="utf-8") == "safe content"

    def test_materialize_does_not_overwrite_existing_files(self, tmp_path: Path) -> None:
        existing_file = tmp_path / "config.json"
        existing_file.write_text('{"user_custom": true}', encoding="utf-8")

        template_files: dict[str, object] = {
            "config.json": '{"user_custom": false}',
            "new_note.txt": "brand new note",
        }

        written = materialize_template_workspace_files(template_files, tmp_path)
        assert "new_note.txt" in written
        assert existing_file.read_text(encoding="utf-8") == '{"user_custom": true}'


class TestAgentPluginImportApiE2E:
    """Tests HTTP preview and confirm endpoints for agent squad plugins."""

    def test_preview_and_confirm_agent_squad(self, client: TestClient, tmp_path: Path) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "squad/plugin.json",
                json.dumps(
                    {
                        "$schema": PLUGIN_SCHEMA,
                        "name": "data-squad",
                        "version": "1.0.0",
                        "entry_agent": "lead-bot",
                    }
                ),
            )
            zf.writestr(
                "squad/agents/lead-bot.md",
                "---\nname: Lead Bot\ndescription: Team Lead\nsubagents:\n  - Worker Bot\n---\nPrompt lead.",
            )
            zf.writestr(
                "squad/agents/worker-bot.md",
                "---\nname: Worker Bot\ndescription: Team Worker\nis_subagent: true\n---\nPrompt worker.",
            )
            zf.writestr("squad/workspace/template.txt", "template data")
        zip_bytes = buf.getvalue()

        mock_worker = SimpleNamespace(id="bot-worker-1", name="Worker Bot")
        mock_lead = SimpleNamespace(id="bot-lead-2", name="Lead Bot")

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.api.plugins.import_.get_evolution_skill_store_db_path",
                return_value=tmp_path / "skills.db",
            ),
            patch(
                "app.services.plugins.import_service._scan_skill_security",
                return_value=[],
            ),
            patch(
                "app.services.agent.agent_service.AgentService.create_agent",
                side_effect=[mock_worker, mock_lead],
            ),
        ):
            preview_res = client.post(
                "/api/v1/plugins/import/preview",
                files={"file": ("squad.zip", zip_bytes, "application/zip")},
            )

            assert preview_res.status_code == 200
            p_body = preview_res.json()
            assert p_body["workspace_file_count"] == 1
            assert len(p_body["agents"]) == 2

            worker = next(a for a in p_body["agents"] if a["name"] == "Worker Bot")
            lead = next(a for a in p_body["agents"] if a["name"] == "Lead Bot")
            assert worker["is_subagent"] is True
            assert lead["is_entry_agent"] is True

            confirm_res = client.post(
                "/api/v1/plugins/import/confirm",
                json={
                    "session_id": p_body["session_id"],
                    "skills": [],
                    "servers": [],
                    "agents": [
                        {
                            "component": "agent",
                            "virtual_id": worker["virtual_id"],
                            "resolution": "install",
                            "name": "Worker Bot",
                        },
                        {
                            "component": "agent",
                            "virtual_id": lead["virtual_id"],
                            "resolution": "install",
                            "name": "Lead Bot",
                        },
                    ],
                    "bind_agent_id": None,
                },
            )

        assert confirm_res.status_code == 200
        c_body = confirm_res.json()
        assert c_body["imported_agents"] == 2
        assert c_body["skipped_agents"] == 0
        assert c_body["created_agent_ids"] == ["bot-worker-1", "bot-lead-2"]
