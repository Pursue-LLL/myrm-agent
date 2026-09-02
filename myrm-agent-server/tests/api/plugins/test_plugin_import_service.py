"""Agent Plugins import service + API tests (business layer).

Covers preview serialization, confirm decisions, skill persistence to
SkillStore, MCP persistence to ``mcpServers`` UserConfig, and agent binding.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.plugins.models import PluginMcpServer, PluginSkill
from myrm_agent_harness.agent.plugins.parser import AgentPluginParser
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType

from app.services.plugins._mcp_persist import (
    _collect_required_secret_keys,
    _server_to_config_dict,
)
from app.services.plugins.import_service import (
    PluginConfirmItem,
    PluginImportSession,
    build_preview_result,
    confirm_plugin_import,
    parse_plugin_zip,
)

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def _plugin_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "demo-plugin/plugin.json",
            json.dumps(
                {
                    "$schema": PLUGIN_SCHEMA,
                    "name": "demo-plugin",
                    "version": "1.0.0",
                    "description": "Demo",
                    "author": {"name": "Acme"},
                }
            ),
        )
        zf.writestr(
            "demo-plugin/skills/summarize/SKILL.md",
            "---\nname: summarize\ndescription: Do summaries\n---\nWork.",
        )
        zf.writestr(
            "demo-plugin/mcp.json",
            json.dumps(
                {
                    "$schema": MCP_SCHEMA,
                    "mcpServers": {
                        "pdf-server": {"type": "stdio", "command": "./bin/pdf"},
                        "remote": {
                            "type": "streamable-http",
                            "url": "https://api.example.com/mcp",
                        },
                    },
                }
            ),
        )
    return buf.getvalue()


def _parse_session() -> PluginImportSession:
    result = parse_plugin_zip(_plugin_zip_bytes())
    skills_by_key = {f"skill:{idx}": skill for idx, skill in enumerate(result.skills)}
    servers_by_key = {f"mcp:{idx}": server for idx, server in enumerate(result.servers)}
    return PluginImportSession(
        plugin_result=result,
        skills_by_key=skills_by_key,
        servers_by_key=servers_by_key,
    )


def _dangerous_plugin_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "danger-plugin/plugin.json",
            json.dumps(
                {
                    "$schema": PLUGIN_SCHEMA,
                    "name": "danger-plugin",
                    "version": "1.0.0",
                    "description": "Dangerous",
                    "author": {"name": "Acme"},
                }
            ),
        )
        zf.writestr(
            "danger-plugin/skills/wipe/SKILL.md",
            "---\nname: wipe\ndescription: Wipe everything\n---\nRun `rm -rf /` to clean up.",
        )
    return buf.getvalue()


class TestParsePluginZip:
    def test_parse_ok(self) -> None:
        result = parse_plugin_zip(_plugin_zip_bytes())
        assert result.meta is not None
        assert result.meta.name == "demo-plugin"
        assert len(result.skills) == 1
        assert len(result.servers) == 2

    def test_archive_security_error_mapped_to_value_error(self) -> None:
        from myrm_agent_harness.backends.skills.scanning.archive_security import (
            ArchiveSecurityError,
        )

        # A zip with > 4096 entries raises ArchiveSecurityError → wrapped as ValueError.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("p/plugin.json", json.dumps({"$schema": PLUGIN_SCHEMA, "name": "big"}))
            for i in range(4200):
                zf.writestr(f"p/skills/s{i:04d}/SKILL.md", "x")
        with pytest.raises(ValueError) as excinfo:
            parse_plugin_zip(buf.getvalue())
        assert not isinstance(excinfo.value, ArchiveSecurityError)

    def test_bad_zip_bytes_mapped_to_value_error(self) -> None:
        """Garbage bytes with a .zip name must surface as a 400-friendly ValueError.

        ``zipfile.BadZipFile`` is not a ``ValueError`` subclass, so this mapping is
        what keeps the preview endpoint from returning a 500 on corrupt uploads.
        """
        with pytest.raises(ValueError, match="valid ZIP"):
            parse_plugin_zip(b"\x00\x01not a real zip")


class TestScanSkillSecurity:
    def _make_skill(self, content: str) -> PluginSkill:
        return PluginSkill(
            name="demo",
            description="Do things",
            content=content,
            files={"SKILL.md": content.encode()},
        )

    def test_clean_skill_passes(self) -> None:
        from app.services.plugins.import_service import _scan_skill_security

        issues = _scan_skill_security(self._make_skill("Just normal work.\n"))
        assert issues == []

    def test_dangerous_pattern_flagged(self) -> None:
        from app.services.plugins.import_service import _scan_skill_security

        issues = _scan_skill_security(self._make_skill("Run `rm -rf /` now.\n"))
        assert len(issues) > 0

    def test_scanner_exception_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from myrm_agent_harness.agent.skills.optimization.config import (
            SecurityConfig,
        )
        from myrm_agent_harness.agent.skills.optimization.security import (
            SkillSecurityValidator,
        )

        from app.services.plugins import import_service as svc

        def _boom(_self: object) -> None:
            raise RuntimeError("scanner exploded")

        monkeypatch.setattr(SkillSecurityValidator, "_compile_patterns", _boom)
        monkeypatch.setattr(
            "myrm_agent_harness.agent.skills.optimization.config.SecurityConfig",
            lambda: SecurityConfig(),
        )
        issues = svc._scan_skill_security(self._make_skill("fine\n"))
        assert len(issues) == 1
        assert "Security scan failed" in issues[0]


class TestBuildPreviewResult:
    def test_preview_shape(self) -> None:
        result = parse_plugin_zip(_plugin_zip_bytes())
        preview = build_preview_result(result)
        assert preview["is_valid"] is True
        assert preview["plugin"]["name"] == "demo-plugin"
        assert preview["plugin"]["version"] == "1.0.0"
        assert preview["skills"][0]["name"] == "summarize"
        assert preview["servers"][0]["name"] == "pdf-server"
        assert preview["servers"][0]["type"] == "stdio"
        assert preview["servers"][1]["type"] == "streamable_http"
        assert all("virtual_id" in s for s in preview["skills"])
        assert all("virtual_id" in s for s in preview["servers"])
        assert isinstance(preview["diagnostics"], list)

    def test_preview_invalid_plugin(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("p/plugin.json", "not json")
        result = AgentPluginParser().parse_zip(buf.getvalue())
        preview = build_preview_result(result)
        assert preview["is_valid"] is False
        assert preview["plugin"]["name"] == ""
        assert any(d["code"] == "manifest_invalid_json" for d in preview["diagnostics"])

    def test_preview_flags_dangerous_skill_content(self) -> None:
        result = parse_plugin_zip(_dangerous_plugin_zip_bytes())
        preview = build_preview_result(result)
        assert len(preview["skills"]) == 1
        skill = preview["skills"][0]
        assert skill["name"] == "wipe"
        assert len(skill["security_issues"]) > 0
        assert any("rm" in issue for issue in skill["security_issues"])

    def test_preview_flags_oversized_skill_content(self) -> None:
        from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

        huge = PluginSkill(
            name="huge",
            description="Too big",
            content="x" * (SkillStore.MAX_SKILL_CONTENT_CHARS + 1),
            files={},
        )
        result = parse_plugin_zip(_plugin_zip_bytes())
        result.skills = [huge]
        preview = build_preview_result(result)
        assert len(preview["skills"]) == 1
        assert preview["skills"][0]["oversized_content"] is True

    def test_preview_marks_normal_skill_not_oversized(self) -> None:
        preview = build_preview_result(parse_plugin_zip(_plugin_zip_bytes()))
        assert preview["skills"][0]["oversized_content"] is False

    def test_preview_marks_conflicting_skill_name(self) -> None:
        result = parse_plugin_zip(_plugin_zip_bytes())
        preview = build_preview_result(result, {"summarize"})
        assert preview["skills"][0]["conflict"] is True

    def test_preview_marks_normal_skill_not_conflicting(self) -> None:
        preview = build_preview_result(parse_plugin_zip(_plugin_zip_bytes()))
        assert preview["skills"][0]["conflict"] is False


class TestServerToConfigDict:
    def _server(self, **overrides: str | list[str] | dict[str, str] | None) -> PluginMcpServer:
        base: dict[str, str | list[str] | dict[str, str] | None] = {
            "name": "srv",
            "server_type": "stdio",
            "command": "./bin/srv",
            "args": None,
            "url": None,
            "headers": None,
            "cwd": None,
            "env_key_names": [],
            "raw_env": {},
        }
        base.update(overrides)
        return PluginMcpServer(**base)

    def test_env_key_names_become_required_secrets(self) -> None:
        cfg = _server_to_config_dict(self._server(env_key_names=["API_KEY", "REGION"]))
        assert cfg["required_secrets"] == ["API_KEY", "REGION"]

    def test_no_env_keys_omit_required_secrets(self) -> None:
        cfg = _server_to_config_dict(self._server())
        assert "required_secrets" not in cfg

    def test_existing_secret_header_ref_preserved(self) -> None:
        cfg = _server_to_config_dict(
            self._server(
                server_type="streamable_http",
                url="https://x",
                headers={"Authorization": "Bearer {{secret:API_TOKEN}}"},
            )
        )
        assert cfg["headers"]["Authorization"] == "Bearer {{secret:API_TOKEN}}"

    def test_plaintext_header_rewritten_to_secret_ref(self) -> None:
        cfg = _server_to_config_dict(
            self._server(
                server_type="streamable_http",
                url="https://x",
                headers={"X-Api-Key": "plain-secret-value"},
            )
        )
        assert cfg["headers"]["X-Api-Key"] == "{{secret:X-Api-Key}}"

    def test_plugin_metadata_embedded_in_extra_params(self) -> None:
        cfg = _server_to_config_dict(
            self._server(),
            plugin_name="demo-plugin",
            plugin_root="/data/plugins/demo-plugin",
            data_root="/data/plugins/demo-plugin_data",
        )
        extra = cfg["extra_params"]
        assert extra["plugin_name"] == "demo-plugin"
        assert extra["plugin_root"] == "/data/plugins/demo-plugin"
        assert extra["data_root"] == "/data/plugins/demo-plugin_data"
        assert "cwd" not in extra  # cwd not set on the server
        assert "env" not in extra

    def test_plugin_metadata_preserves_cwd_and_env(self) -> None:
        cfg = _server_to_config_dict(
            self._server(cwd="./workdir", raw_env={"FOO": "bar"}),
            plugin_name="demo-plugin",
            plugin_root="/root",
            data_root="/data",
        )
        extra = cfg["extra_params"]
        assert extra["cwd"] == "./workdir"
        assert extra["env"] == {"FOO": "bar"}

    def test_plugin_metadata_omitted_without_name(self) -> None:
        cfg = _server_to_config_dict(self._server())
        assert "extra_params" not in cfg


class TestCollectRequiredSecretKeys:
    def test_dedupes_env_and_header_refs(self) -> None:
        configs: list[dict[str, object]] = [
            {"required_secrets": ["API_TOKEN", "REGION"]},
            {
                "required_secrets": ["REGION"],
                "headers": {
                    "Authorization": "Bearer {{secret:API_TOKEN}}",
                    "X-Region": "{{secret:REGION}}",
                },
            },
            {"name": "plain"},
        ]
        assert _collect_required_secret_keys(configs) == ["API_TOKEN", "REGION"]

    def test_empty_when_no_secrets(self) -> None:
        assert _collect_required_secret_keys([{"name": "srv"}]) == []


class TestConfirmPluginImport:
    def _make_session(self) -> PluginImportSession:
        return _parse_session()

    async def test_confirm_installs_skills_and_servers(self, tmp_path: Path) -> None:
        session = self._make_session()
        skill_keys = list(session.skills_by_key.keys())
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
        )
        agent_service = SimpleNamespace(
            get_agent_by_id=AsyncMock(return_value=SimpleNamespace(metadata={"mcp_ids": ["existing"]})),
            update_agent=AsyncMock(),
        )

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
            patch("app.core.channel_bridge.config_cache.invalidate_user_configs_cache") as invalidate_cache,
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[
                    PluginConfirmItem(
                        component="skill",
                        virtual_id=skill_keys[0],
                        resolution="install",
                        name="summarize",
                    ),
                ],
                server_decisions=[
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[0],
                        resolution="install",
                        name="pdf-server",
                    ),
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[1],
                        resolution="skip",
                        name="remote",
                    ),
                ],
                bind_agent_id="agent-1",
            )

        assert result == {
            "imported_skills": 1,
            "skipped_skills": 0,
            "imported_servers": 1,
            "skipped_servers": 1,
            "imported_agents": 0,
            "skipped_agents": 0,
            "created_agent_ids": [],
            "required_secret_keys": [],
        }

        # Skills persisted to SkillStore.
        fake_store.save_skills_batch.assert_awaited_once()
        records = fake_store.save_skills_batch.await_args.args[0]
        assert len(records) == 1
        assert records[0].name == "summarize"
        assert records[0].path == "plugins/demo-plugin/summarize/SKILL.md"

        # MCP config read + write.
        config_service.get.assert_awaited_once_with("mcpServers")
        config_service.set.assert_awaited_once()
        set_args = config_service.set.await_args.args
        set_kwargs = config_service.set.await_args.kwargs
        assert set_args[0] == "mcpServers"
        persisted_value = set_args[1]
        assert set_kwargs["device_id"] == "plugin-import"
        # mcpServers contract is {mcpConfigs: [...]}; a bare list would be
        # unreadable by the frontend / runtime config loader.
        assert set(persisted_value) == {"mcpConfigs"}
        persisted = persisted_value["mcpConfigs"]
        assert len(persisted) == 1
        assert persisted[0]["name"] == "pdf-server"
        assert persisted[0]["enabled"] is False
        assert persisted[0]["command"] == "./bin/pdf"
        # Import invalidates the runtime config cache so MCP loads promptly.
        invalidate_cache.assert_called_once()

        # Agent binding appends only installed server names.
        agent_service.update_agent.assert_awaited_once()
        update = agent_service.update_agent.await_args.args[1]
        assert update.mcp_ids == ["existing", "pdf-server"]

    async def test_confirm_duplicate_server_name_not_counted_or_bound(self, tmp_path: Path) -> None:
        session = self._make_session()
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(value={"mcpConfigs": [{"name": "pdf-server", "enabled": True}]})),
            set=AsyncMock(),
        )
        agent_service = SimpleNamespace(
            get_agent_by_id=AsyncMock(return_value=SimpleNamespace(metadata={"mcp_ids": ["existing"]})),
            update_agent=AsyncMock(),
        )

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
            patch("app.core.channel_bridge.config_cache.invalidate_user_configs_cache") as invalidate_cache,
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[],
                server_decisions=[
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[0],
                        resolution="install",
                        name="pdf-server",
                    ),
                ],
                bind_agent_id="agent-1",
            )

        # pdf-server already exists -> skipped, not counted, not bound.
        assert result == {
            "imported_skills": 0,
            "skipped_skills": 0,
            "imported_servers": 0,
            "skipped_servers": 0,
            "imported_agents": 0,
            "skipped_agents": 0,
            "created_agent_ids": [],
            "required_secret_keys": [],
        }
        config_service.set.assert_not_awaited()
        invalidate_cache.assert_not_called()
        agent_service.update_agent.assert_not_awaited()

    async def test_confirm_skip_everything(self, tmp_path: Path) -> None:
        session = self._make_session()
        skill_keys = list(session.skills_by_key.keys())
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[
                    PluginConfirmItem(
                        component="skill",
                        virtual_id=skill_keys[0],
                        resolution="skip",
                        name="summarize",
                    ),
                ],
                server_decisions=[
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[0],
                        resolution="skip",
                        name="pdf-server",
                    ),
                ],
                bind_agent_id=None,
            )

        assert result == {
            "imported_skills": 0,
            "skipped_skills": 1,
            "imported_servers": 0,
            "skipped_servers": 1,
            "imported_agents": 0,
            "skipped_agents": 0,
            "created_agent_ids": [],
            "required_secret_keys": [],
        }
        fake_store.save_skills_batch.assert_not_awaited()
        config_service.set.assert_not_awaited()
        agent_service.update_agent.assert_not_awaited()

    async def test_confirm_merges_existing_mcp_configs(self, tmp_path: Path) -> None:
        session = self._make_session()
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(value={"mcpConfigs": [{"name": "pdf-server", "enabled": True, "command": "/old"}]})
            ),
            set=AsyncMock(),
        )
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
            patch("app.core.channel_bridge.config_cache.invalidate_user_configs_cache") as invalidate_cache,
        ):
            await confirm_plugin_import(
                session,
                skill_decisions=[],
                server_decisions=[
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[0],
                        resolution="install",
                        name="pdf-server",
                    ),
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[1],
                        resolution="install",
                        name="remote",
                    ),
                ],
                bind_agent_id=None,
            )

        set_args = config_service.set.await_args.args
        persisted_value = set_args[1]
        # Existing pdf-server kept as-is; remote appended (skipping the duplicate).
        names = [cfg["name"] for cfg in persisted_value["mcpConfigs"]]
        assert names == ["pdf-server", "remote"]
        assert persisted_value["mcpConfigs"][1]["enabled"] is False
        assert persisted_value["mcpConfigs"][1]["type"] == "streamable_http"
        assert persisted_value["mcpConfigs"][1]["url"] == "https://api.example.com/mcp"
        invalidate_cache.assert_called_once()

    async def test_confirm_preserves_legacy_bare_list_mcp_configs(self, tmp_path: Path) -> None:
        """User-configured servers (incl. legacy bare-list payloads) survive import.

        The persisted shape is always ``{"mcpConfigs": [...]}`` and existing names
        are merged with imported ones, never dropped.
        """
        session = self._make_session()
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(value=[{"name": "user-mcp", "enabled": True, "command": "/keep-me"}])),
            set=AsyncMock(),
        )
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
            patch("app.core.channel_bridge.config_cache.invalidate_user_configs_cache") as invalidate_cache,
        ):
            await confirm_plugin_import(
                session,
                skill_decisions=[],
                server_decisions=[
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[0],
                        resolution="install",
                        name="pdf-server",
                    ),
                ],
                bind_agent_id=None,
            )

        set_args = config_service.set.await_args.args
        persisted_value = set_args[1]
        names = [cfg["name"] for cfg in persisted_value["mcpConfigs"]]
        assert names == ["user-mcp", "pdf-server"]
        assert persisted_value["mcpConfigs"][0]["command"] == "/keep-me"
        invalidate_cache.assert_called_once()

    async def test_confirm_skips_skill_with_security_issues(self, tmp_path: Path) -> None:
        session = _parse_session()
        skill_keys = list(session.skills_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
            patch(
                "app.services.plugins.import_service._scan_skill_security",
                return_value=["Dangerous pattern detected"],
            ),
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[
                    PluginConfirmItem(
                        component="skill",
                        virtual_id=skill_keys[0],
                        resolution="install",
                        name="summarize",
                    ),
                ],
                server_decisions=[],
                bind_agent_id=None,
            )

        assert result == {
            "imported_skills": 0,
            "skipped_skills": 1,
            "imported_servers": 0,
            "skipped_servers": 0,
            "imported_agents": 0,
            "skipped_agents": 0,
            "created_agent_ids": [],
            "required_secret_keys": [],
        }
        fake_store.save_skills_batch.assert_not_awaited()
        config_service.set.assert_not_awaited()

    async def test_confirm_skips_oversized_skill_content(self, tmp_path: Path) -> None:
        from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

        session = _parse_session()
        skill_keys = list(session.skills_by_key.keys())
        session.skills_by_key[skill_keys[0]] = PluginSkill(
            name="huge",
            description="Too big",
            content="x" * (SkillStore.MAX_SKILL_CONTENT_CHARS + 1),
            files={},
        )

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[
                    PluginConfirmItem(
                        component="skill",
                        virtual_id=skill_keys[0],
                        resolution="install",
                        name="huge",
                    ),
                ],
                server_decisions=[],
                bind_agent_id=None,
            )

        assert result == {
            "imported_skills": 0,
            "skipped_skills": 1,
            "imported_servers": 0,
            "skipped_servers": 0,
            "imported_agents": 0,
            "skipped_agents": 0,
            "created_agent_ids": [],
            "required_secret_keys": [],
        }
        fake_store.save_skills_batch.assert_not_awaited()
        config_service.set.assert_not_awaited()

    async def test_confirm_upgrades_existing_skill_in_place(self, tmp_path: Path) -> None:
        """A same-name skill is upgraded in place instead of duplicated.

        The authoritative existing map is re-queried at confirm time, so even an
        ``install`` decision on a conflict resolves to an in-place overwrite.
        """
        session = _parse_session()
        skill_keys = list(session.skills_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={"summarize": "existing-skill-id"},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[
                    PluginConfirmItem(
                        component="skill",
                        virtual_id=skill_keys[0],
                        resolution="install",
                        name="summarize",
                    ),
                ],
                server_decisions=[],
                bind_agent_id=None,
            )

        assert result == {
            "imported_skills": 1,
            "skipped_skills": 0,
            "imported_servers": 0,
            "skipped_servers": 0,
            "imported_agents": 0,
            "skipped_agents": 0,
            "created_agent_ids": [],
            "required_secret_keys": [],
        }
        fake_store.save_skills_batch.assert_awaited_once()
        records = fake_store.save_skills_batch.await_args.args[0]
        assert len(records) == 1
        record = records[0]
        # Reuses the existing skill_id and records a DERIVED lineage from it.
        assert record.skill_id == "existing-skill-id"
        assert record.lineage.evolution_type == EvolutionType.DERIVED
        assert record.lineage.parent_id == "existing-skill-id"

    async def test_confirm_explicit_replace_resolution_upgrades(self, tmp_path: Path) -> None:
        """An explicit ``replace`` decision has the same in-place semantics."""
        session = _parse_session()
        skill_keys = list(session.skills_by_key.keys())

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={"summarize": "existing-skill-id"},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[
                    PluginConfirmItem(
                        component="skill",
                        virtual_id=skill_keys[0],
                        resolution="replace",
                        name="summarize",
                    ),
                ],
                server_decisions=[],
                bind_agent_id=None,
            )

        assert result["imported_skills"] == 1
        records = fake_store.save_skills_batch.await_args.args[0]
        record = records[0]
        assert record.skill_id == "existing-skill-id"
        assert record.lineage.evolution_type == EvolutionType.DERIVED
        assert record.lineage.parent_id == "existing-skill-id"

    async def test_confirm_persists_scoped_secrets_and_headers(self, tmp_path: Path) -> None:
        """Imported servers persist required_secrets and secret header refs.

        ``env_key_names`` become ``required_secrets`` for runtime Scoped Secret
        Injection, and header values that are already ``{{secret:KEY}}`` refs are
        preserved verbatim while plaintext values are rewritten to refs, so
        credentials never land in the store as plaintext.
        """
        session = _parse_session()
        server_keys = list(session.servers_by_key.keys())
        session.servers_by_key[server_keys[0]] = PluginMcpServer(
            name="auth-server",
            server_type="streamable_http",
            command=None,
            args=None,
            url="https://api.example.com/mcp",
            headers={
                "Authorization": "Bearer {{secret:API_TOKEN}}",
                "X-Client": "keep-plain",
            },
            cwd=None,
            env_key_names=["API_TOKEN", "REGION"],
            raw_env={},
        )

        fake_store = SimpleNamespace(
            db_path=tmp_path,
            save_skills_batch=AsyncMock(),
            get_active_skills=lambda: [],
        )
        config_service = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
        agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())

        with (
            patch(
                "app.services.plugins.import_service._load_existing_skill_ids",
                return_value={},
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
            patch("app.core.channel_bridge.config_cache.invalidate_user_configs_cache") as invalidate_cache,
        ):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[],
                server_decisions=[
                    PluginConfirmItem(
                        component="mcp",
                        virtual_id=server_keys[0],
                        resolution="install",
                        name="auth-server",
                    ),
                ],
                bind_agent_id=None,
            )

        assert result["imported_servers"] == 1
        # env_key_names + header refs (incl. rewritten plaintext refs), deduped.
        assert result["required_secret_keys"] == ["API_TOKEN", "REGION", "X-Client"]

        set_args = config_service.set.await_args.args
        persisted_value = set_args[1]
        entry = persisted_value["mcpConfigs"][0]
        assert entry["required_secrets"] == ["API_TOKEN", "REGION"]
        # Existing secret ref preserved verbatim; plaintext rewritten to a ref.
        assert entry["headers"]["Authorization"] == "Bearer {{secret:API_TOKEN}}"
        assert entry["headers"]["X-Client"] == "{{secret:X-Client}}"
        invalidate_cache.assert_called_once()


class TestPluginStaging:
    def test_roundtrip(self, tmp_path: Path) -> None:
        from app.services.plugins.import_service import PluginStaging

        staging = PluginStaging(tmp_path)
        session = _parse_session()
        staging.save_session("sess-1", session)
        loaded = staging.load_session("sess-1")
        assert loaded.plugin_result.meta is not None
        assert loaded.plugin_result.meta.name == "demo-plugin"
        assert len(loaded.skills_by_key) == 1
        assert len(loaded.servers_by_key) == 2
        staging.cleanup_session("sess-1")
        assert not (tmp_path / "plugin_staging" / "sess-1.pkl").exists()

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        from app.services.plugins.import_service import PluginStaging

        staging = PluginStaging(tmp_path)
        with pytest.raises(FileNotFoundError):
            staging.load_session("nope")

    def test_cleanup_expired_sessions(self, tmp_path: Path) -> None:
        from app.services.plugins.import_service import PluginStaging

        staging = PluginStaging(tmp_path)
        session = _parse_session()
        staging.save_session("old-session", session)
        staging.save_session("new-session", session)

        # Backdate the old-session file beyond the 24h TTL.
        old_file = tmp_path / "plugin_staging" / "old-session.pkl"
        old_mtime = time.time() - 86400 * 2
        os.utime(old_file, (old_mtime, old_mtime))

        asyncio.run(staging.cleanup_expired_sessions())

        assert not old_file.exists()
        assert (tmp_path / "plugin_staging" / "new-session.pkl").exists()


class TestPluginFiles:
    """Bundled-file persistence: decision, write, containment, removal."""

    def _stdio_server(self, **overrides: object) -> PluginMcpServer:
        base: dict[str, object] = {
            "name": "srv",
            "server_type": "stdio",
            "command": None,
            "args": None,
            "url": None,
            "headers": None,
            "cwd": None,
            "env_key_names": [],
            "raw_env": {},
        }
        base.update(overrides)
        return PluginMcpServer(**base)

    def test_server_needs_bundled_files_dot_command(self) -> None:
        from app.services.plugins._plugin_files import server_needs_bundled_files

        assert server_needs_bundled_files(self._stdio_server(command="./bin/pdf")) is True

    def test_server_needs_bundled_files_placeholders(self) -> None:
        from app.services.plugins._plugin_files import server_needs_bundled_files

        assert server_needs_bundled_files(self._stdio_server(command="python", args=["${PLUGIN_ROOT}/server.py"])) is True
        assert server_needs_bundled_files(self._stdio_server(command="python", raw_env={"DATA": "${PLUGIN_DATA}"})) is True

    def test_server_needs_bundled_files_plain_stdio_and_remote(self) -> None:
        from app.services.plugins._plugin_files import server_needs_bundled_files

        assert server_needs_bundled_files(self._stdio_server(command="python -m mcp")) is False
        assert (
            server_needs_bundled_files(
                self._stdio_server(
                    server_type="streamable_http",
                    command=None,
                    url="https://api.example.com/mcp",
                )
            )
            is False
        )

    def test_persist_writes_and_returns_roots(self, tmp_path: Path) -> None:
        from app.services.plugins._plugin_files import (
            persist_plugin_files,
            plugin_data_dir,
            plugin_installed_dir,
        )

        files = {
            "bin/pdf": b"#!/bin/sh\necho ok",
            "plugin.json": b"{}",
            "mcp.json": b"{}",
        }
        roots = persist_plugin_files("demo-plugin", files, tmp_path)
        assert roots is not None
        root_dir, data_dir = roots
        assert Path(root_dir) == plugin_installed_dir(tmp_path, "demo-plugin")
        assert Path(data_dir) == plugin_data_dir(tmp_path, "demo-plugin")
        assert (Path(root_dir) / "bin" / "pdf").read_bytes() == files["bin/pdf"]
        assert (Path(root_dir) / "plugin.json").read_bytes() == b"{}"
        assert Path(data_dir).is_dir()

    def test_persist_rejects_traversal(self, tmp_path: Path) -> None:
        from app.services.plugins._plugin_files import persist_plugin_files

        roots = persist_plugin_files(
            "demo-plugin",
            {"../escape.txt": b"nope", "ok.txt": b"yes"},
            tmp_path,
        )
        assert roots is not None
        root_dir = Path(roots[0])
        assert not (root_dir.parent / "escape.txt").exists()
        assert (root_dir / "ok.txt").read_bytes() == b"yes"

    def test_persist_rejects_unsafe_name(self, tmp_path: Path) -> None:
        from app.services.plugins._plugin_files import persist_plugin_files

        with pytest.raises(ValueError):
            persist_plugin_files("..", {"a": b"b"}, tmp_path)
        with pytest.raises(ValueError):
            persist_plugin_files("Bad Name", {"a": b"b"}, tmp_path)

    def test_persist_none_when_no_files(self, tmp_path: Path) -> None:
        from app.services.plugins._plugin_files import persist_plugin_files

        assert persist_plugin_files("demo-plugin", {}, tmp_path) is None

    def test_remove_plugin_files(self, tmp_path: Path) -> None:
        from app.services.plugins._plugin_files import (
            persist_plugin_files,
            plugin_data_dir,
            plugin_installed_dir,
            remove_plugin_files,
        )

        persist_plugin_files("demo-plugin", {"a.txt": b"x"}, tmp_path)
        assert plugin_installed_dir(tmp_path, "demo-plugin").exists()
        assert plugin_data_dir(tmp_path, "demo-plugin").exists()

        assert remove_plugin_files("demo-plugin", tmp_path) is True
        assert not plugin_installed_dir(tmp_path, "demo-plugin").exists()
        assert not plugin_data_dir(tmp_path, "demo-plugin").exists()
        # Second removal is a no-op.
        assert remove_plugin_files("demo-plugin", tmp_path) is False

    def test_plugin_dir_exists(self, tmp_path: Path) -> None:
        from app.services.plugins._plugin_files import (
            persist_plugin_files,
            plugin_dir_exists,
        )

        assert plugin_dir_exists(tmp_path, "demo-plugin") is False
        persist_plugin_files("demo-plugin", {"a.txt": b"x"}, tmp_path)
        assert plugin_dir_exists(tmp_path, "demo-plugin") is True


class TestListAndUninstallPlugins:
    async def test_list_installed_plugins_groups_by_provenance(self) -> None:
        from app.services.plugins.import_service import list_installed_plugins

        config_service = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    value={
                        "mcpConfigs": [
                            {
                                "name": "pdf-server",
                                "extra_params": {"plugin_name": "demo-plugin"},
                            },
                            {
                                "name": "remote",
                                "extra_params": {
                                    "plugin_name": "demo-plugin",
                                    "plugin_root": "/x",
                                },
                                "enabled": True,
                            },
                            {"name": "user-mcp", "command": "/keep"},
                        ]
                    }
                )
            ),
            set=AsyncMock(),
        )
        with (
            patch("app.services.config.service.config_service", config_service),
            patch(
                "app.services.plugins.import_service._plugin_dir_exists",
                side_effect=lambda name: name == "demo-plugin",
            ),
        ):
            items = await list_installed_plugins()

        assert items == [
            {
                "name": "demo-plugin",
                "servers": ["pdf-server", "remote"],
                "server_meta": [
                    {"name": "pdf-server", "enabled": False},
                    {"name": "remote", "enabled": True},
                ],
                "has_bundled_files": True,
            }
        ]

    async def test_list_installed_plugins_empty(self) -> None:
        from app.services.plugins.import_service import list_installed_plugins

        config_service = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(value={"mcpConfigs": []})),
            set=AsyncMock(),
        )
        with patch("app.services.config.service.config_service", config_service):
            assert await list_installed_plugins() == []

    async def test_uninstall_removes_servers_bindings_and_files(self, tmp_path: Path) -> None:
        from app.services.plugins.import_service import uninstall_plugin

        config_service = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    value={
                        "mcpConfigs": [
                            {
                                "name": "pdf-server",
                                "extra_params": {"plugin_name": "demo-plugin"},
                            },
                            {"name": "user-mcp", "command": "/keep"},
                        ]
                    }
                )
            ),
            set=AsyncMock(),
        )
        agent_repo = SimpleNamespace(
            list_profiles=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        id="agent-1",
                        metadata={"mcp_ids": ["pdf-server", "user-mcp"]},
                    ),
                    SimpleNamespace(id="agent-2", metadata={"mcp_ids": []}),
                ]
            ),
            update_profile=AsyncMock(),
        )
        uow_mock = MagicMock()
        uow_mock.agent_repo = agent_repo
        uow_mock.__aenter__ = AsyncMock(return_value=uow_mock)
        uow_mock.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.config.service.config_service", config_service),
            patch(
                "app.database.repositories.uow.UnitOfWork",
                return_value=uow_mock,
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store_db_path",
                return_value=tmp_path / "skills.db",
            ),
        ):
            result = await uninstall_plugin("demo-plugin")

        assert result == {
            "plugin_name": "demo-plugin",
            "removed_servers": 1,
            "unbound_agents": 1,
            "evicted_tools": 0,
            "purged_cron_jobs": 0,
            "paused_cron_jobs": 0,
            "removed_files": False,
        }
        # Only the plugin's server is removed; user-mcp survives.
        set_args = config_service.set.await_args.args
        persisted = set_args[1]["mcpConfigs"]
        assert [cfg["name"] for cfg in persisted] == ["user-mcp"]
        # Agent binding drops the uninstalled server name only.
        call_args = agent_repo.update_profile.await_args.args
        assert call_args[0] == "agent-1"
        assert call_args[1]["metadata"]["mcp_ids"] == ["user-mcp"]

    async def test_uninstall_missing_plugin_noop(self, tmp_path: Path) -> None:
        from app.services.plugins.import_service import uninstall_plugin

        config_service = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(value={"mcpConfigs": [{"name": "user-mcp", "command": "/keep"}]})),
            set=AsyncMock(),
        )
        with (
            patch("app.services.config.service.config_service", config_service),
            patch(
                "app.services.plugins._mcp_persist._unbind_plugin_from_agents",
                AsyncMock(return_value=0),
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store_db_path",
                return_value=tmp_path / "skills.db",
            ),
            patch(
                "app.services.plugins._plugin_files.remove_plugin_files",
                return_value=False,
            ),
        ):
            result = await uninstall_plugin("nope")

        assert result == {
            "plugin_name": "nope",
            "removed_servers": 0,
            "unbound_agents": 0,
            "evicted_tools": 0,
            "purged_cron_jobs": 0,
            "paused_cron_jobs": 0,
            "removed_files": False,
        }
        config_service.set.assert_not_awaited()

    async def test_uninstall_refuses_unsafe_name(self) -> None:
        """Uninstall with a path-traversal name must be a safe no-op."""
        from app.services.plugins.import_service import uninstall_plugin

        result = await uninstall_plugin("../important_dir")

        assert result == {
            "plugin_name": "../important_dir",
            "removed_servers": 0,
            "unbound_agents": 0,
            "evicted_tools": 0,
            "purged_cron_jobs": 0,
            "paused_cron_jobs": 0,
            "removed_files": False,
        }

    def test_remove_plugin_files_refuses_unsafe_name(self, tmp_path: Path) -> None:
        """File removal must never touch paths derived from an unsafe name."""
        from app.services.plugins._plugin_files import remove_plugin_files

        victim = tmp_path / "important_dir"
        victim.mkdir()
        (victim / "file.txt").write_text("keep")
        assert remove_plugin_files("../important_dir", tmp_path) is False
        assert (victim / "file.txt").exists()

    async def test_uninstall_performs_4d_eviction(self, tmp_path: Path) -> None:
        """Verify uninstall executes full 4D capability eviction pipeline."""
        from myrm_agent_harness.api import (
            MCPAnnotations,
            SafetyMetadata,
            get_ptc_safety_metadata,
            register_ptc_safety_metadata,
        )

        from app.services.plugins.import_service import uninstall_plugin

        plugin_name = "test-evict-plugin"
        server_name = "test-evict-server"
        tool_name = "test_evict_tool"

        # Setup registered PTC tool
        register_ptc_safety_metadata(plugin_name, tool_name, SafetyMetadata(), MCPAnnotations())
        assert get_ptc_safety_metadata(plugin_name, tool_name) is not None

        config_service = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    value={
                        "mcpConfigs": [
                            {
                                "name": server_name,
                                "command": "/bin/test",
                                "extra_params": {"plugin_name": plugin_name},
                            }
                        ]
                    }
                )
            ),
            set=AsyncMock(),
        )

        mock_cron_manager = SimpleNamespace(
            list_jobs=AsyncMock(return_value=[]),
            delete_job=AsyncMock(return_value=True),
            update_job=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.config.service.config_service", config_service),
            patch(
                "app.services.plugins._mcp_persist._unbind_plugin_from_agents",
                AsyncMock(return_value=1),
            ),
            patch(
                "app.core.cron.adapters.setup.get_cron_manager",
                return_value=mock_cron_manager,
            ),
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store_db_path",
                return_value=tmp_path / "skills.db",
            ),
            patch(
                "app.services.plugins._plugin_files.remove_plugin_files",
                return_value=True,
            ),
        ):
            res = await uninstall_plugin(plugin_name)

        assert res["plugin_name"] == plugin_name
        assert res["removed_servers"] == 1
        assert res["unbound_agents"] == 1
        assert res["evicted_tools"] >= 1
        assert res["removed_files"] is True
        # Tool metadata is now completely gone from memory
        assert get_ptc_safety_metadata(plugin_name, tool_name) is None


class TestAgentPluginImportWithAgents:
    """Tests importing plugins that declare agents/*.md and workspace/ assets."""

    @pytest.mark.asyncio
    async def test_confirm_import_agents_and_subagents(self, tmp_path: Path) -> None:
        zip_bytes = _plugin_zip_with_agents_bytes()
        result = parse_plugin_zip(zip_bytes)
        skills_by_key = {f"skill:{idx}": skill for idx, skill in enumerate(result.skills)}
        servers_by_key = {f"mcp:{idx}": server for idx, server in enumerate(result.servers)}
        agents_by_key = {f"agent:{idx}": agent for idx, agent in enumerate(result.agents)}

        session = PluginImportSession(
            plugin_result=result,
            skills_by_key=skills_by_key,
            servers_by_key=servers_by_key,
            agents_by_key=agents_by_key,
        )

        agent_decisions = [
            PluginConfirmItem(
                component="agent",
                virtual_id=f"agent:{idx}",
                resolution="install",
                name=agent.name,
            )
            for idx, agent in enumerate(result.agents)
        ]

        mock_created_agents = [
            SimpleNamespace(id="agent-sub-1", name="Data Extractor"),
            SimpleNamespace(id="agent-lead-1", name="Lead Analyst"),
        ]

        with (
            patch("app.services.agent.agent_service.AgentService.create_agent", side_effect=mock_created_agents) as mock_create,
            patch("app.services.plugins.import_service._write_skills", AsyncMock()),
            patch("app.services.plugins.import_service._load_existing_skill_ids", return_value={}),
        ):
            res = await confirm_plugin_import(
                session,
                skill_decisions=[],
                server_decisions=[],
                agent_decisions=agent_decisions,
            )

        assert res["imported_agents"] == 2
        assert res["skipped_agents"] == 0
        assert res["created_agent_ids"] == ["agent-sub-1", "agent-lead-1"]
        assert mock_create.call_count == 2


def _plugin_zip_with_agents_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "agent-squad/plugin.json",
            json.dumps(
                {
                    "$schema": PLUGIN_SCHEMA,
                    "name": "agent-squad",
                    "version": "1.0.0",
                    "entry_agent": "lead-analyst",
                }
            ),
        )
        zf.writestr(
            "agent-squad/agents/lead-analyst.md",
            "---\nname: Lead Analyst\ndescription: Lead coordinator\nsubagents:\n  - Data Extractor\n---\nPrompt lead.",
        )
        zf.writestr(
            "agent-squad/agents/data-extractor.md",
            "---\nname: Data Extractor\ndescription: Extractor\nis_subagent: true\n---\nPrompt sub.",
        )
        zf.writestr(
            "agent-squad/workspace/template.xlsx",
            "dummy_xlsx",
        )
    return buf.getvalue()
