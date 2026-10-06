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

from app.core.skills.providers.local import compute_local_skill_id
from app.services.plugins._gates import scan_skill_security
from app.services.plugins._mcp_persist import (
    _collect_required_secret_keys,
    _server_to_config_dict,
)
from app.services.plugins._preview_context import PreviewContext
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
            "demo-plugin/bin/pdf",
            "#!/bin/sh\necho pdf\n",
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
        issues = scan_skill_security(self._make_skill("Just normal work.\n"))
        assert issues == []

    def test_dangerous_pattern_flagged(self) -> None:
        issues = scan_skill_security(self._make_skill("Run `rm -rf /` now.\n"))
        assert len(issues) > 0

    def test_scanner_exception_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from myrm_agent_harness.agent.skills.optimization.config import (
            SecurityConfig,
        )
        from myrm_agent_harness.agent.skills.optimization.security import (
            SkillSecurityValidator,
        )

        def _boom(_self: object) -> None:
            raise RuntimeError("scanner exploded")

        monkeypatch.setattr(SkillSecurityValidator, "_compile_patterns", _boom)
        monkeypatch.setattr(
            "myrm_agent_harness.agent.skills.optimization.config.SecurityConfig",
            lambda: SecurityConfig(),
        )
        issues = scan_skill_security(self._make_skill("fine\n"))
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
        preview = build_preview_result(result, PreviewContext(local_skill_names=frozenset({"summarize"})))
        assert preview["skills"][0]["conflict"] is True

    def test_preview_marks_normal_skill_not_conflicting(self) -> None:
        preview = build_preview_result(parse_plugin_zip(_plugin_zip_bytes()))
        assert preview["skills"][0]["conflict"] is False

    def test_preview_includes_capabilities_and_effective_tier(self) -> None:
        preview = build_preview_result(parse_plugin_zip(_plugin_zip_bytes()))
        assert "capabilities" in preview["plugin"]
        assert "effective_tier" in preview["plugin"]
        assert "risk_level" in preview["plugin"]
        # demo-plugin has a stdio server in bin/pdf -> inferred shell_exec
        assert preview["plugin"]["effective_tier"] == "shell_exec"
        assert preview["plugin"]["risk_level"] == "high"
        assert len(preview["servers"]) == 2
        server_types = {s["name"]: s["capabilities"] for s in preview["servers"]}
        assert "shell_exec" in server_types["pdf-server"]
        assert "network" in server_types["remote"]

    def test_preview_includes_diagnostics_when_privilege_undeclared(self) -> None:
        # Create a plugin zip where manifest declared read_only but has stdio server
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "sneaky-plugin/plugin.json",
                json.dumps(
                    {
                        "$schema": PLUGIN_SCHEMA,
                        "name": "sneaky-plugin",
                        "version": "1.0.0",
                        "capabilities": ["read_only"],
                    }
                ),
            )
            zf.writestr(
                "sneaky-plugin/mcp.json",
                json.dumps(
                    {
                        "$schema": MCP_SCHEMA,
                        "mcpServers": {
                            "runner": {
                                "type": "stdio",
                                "command": "./tool.sh",
                            }
                        },
                    }
                ),
            )
            zf.writestr("sneaky-plugin/tool.sh", "#!/bin/sh\necho hi")
        preview = build_preview_result(parse_plugin_zip(buf.getvalue()))
        diag_codes = [d["code"] for d in preview["diagnostics"]]
        assert "capability_undeclared_privilege" in diag_codes
        assert preview["plugin"]["risk_level"] == "high"


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


def _decision(component: str, virtual_id: str, name: str, resolution: str = "install") -> PluginConfirmItem:
    return PluginConfirmItem(component=component, virtual_id=virtual_id, resolution=resolution, name=name)


EMPTY_RESULT: dict[str, object] = {
    "imported_skills": 0,
    "skipped_skills": 0,
    "imported_servers": 0,
    "skipped_servers": 0,
    "imported_agents": 0,
    "skipped_agents": 0,
    "created_agent_ids": [],
    "required_secret_keys": [],
    "agents": [],
    "failures": [],
}


@pytest.fixture
def confirm_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Hermetic collaborators of ``confirm_plugin_import``: skills install under ``tmp_path``, services faked."""
    skills_dir = tmp_path / "installed-skills"
    skills_dir.mkdir()
    monkeypatch.setattr("myrm_agent_harness.agent.skills.market.service.LOCAL_INSTALL_DIR", skills_dir)
    mount = AsyncMock(return_value=SimpleNamespace(mounted=True, error=None))
    monkeypatch.setattr("app.core.skills.discovery.mount.maybe_mount_after_install", mount)
    monkeypatch.setattr(
        "app.core.skills.store.evolution_store.get_evolution_skill_store",
        lambda: SimpleNamespace(get_active_skills=lambda: [], delete_skill=AsyncMock()),
    )
    monkeypatch.setattr(
        "app.core.skills.store.evolution_store.get_evolution_skill_store_db_path",
        lambda: tmp_path / "skills.db",
    )
    monkeypatch.setattr(
        "app.services.plugins.import_service.load_preview_context",
        AsyncMock(return_value=PreviewContext()),
    )
    config_service = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
    agent_service = SimpleNamespace(get_agent_by_id=AsyncMock(), update_agent=AsyncMock())
    invalidate_cache = MagicMock()
    monkeypatch.setattr("app.services.config.service.config_service", config_service)
    monkeypatch.setattr("app.services.agent.agent_service.AgentService", agent_service)
    monkeypatch.setattr("app.core.channel_bridge.config_cache.invalidate_user_configs_cache", invalidate_cache)
    return SimpleNamespace(
        skills_dir=skills_dir,
        mount=mount,
        config_service=config_service,
        agent_service=agent_service,
        invalidate_cache=invalidate_cache,
    )


class TestConfirmPluginImport:
    async def test_installs_skill_through_the_pipeline_servers_disabled_and_binds_expert(
        self, confirm_env: SimpleNamespace
    ) -> None:
        session = _parse_session()
        skill_key = next(iter(session.skills_by_key))
        server_keys = list(session.servers_by_key)
        confirm_env.agent_service.get_agent_by_id.return_value = SimpleNamespace(
            skills=["existing-skill"], metadata={"mcp_ids": ["existing"]}
        )

        result = await confirm_plugin_import(
            session,
            skill_decisions=[_decision("skill", skill_key, "summarize")],
            server_decisions=[
                _decision("mcp", server_keys[0], "pdf-server"),
                _decision("mcp", server_keys[1], "remote", "skip"),
            ],
            bind_agent_id="agent-1",
        )

        assert result == {**EMPTY_RESULT, "imported_skills": 1, "imported_servers": 1, "skipped_servers": 1}

        # The skill is a real installed skill (files on disk, enabled in the catalog), not a database stub.
        skill_dir = confirm_env.skills_dir / "summarize"
        assert (skill_dir / "SKILL.md").is_file()
        confirm_env.mount.assert_awaited_once()

        confirm_env.config_service.get.assert_awaited_once_with("mcpServers")
        confirm_env.config_service.set.assert_awaited_once()
        set_args = confirm_env.config_service.set.await_args.args
        assert set_args[0] == "mcpServers"
        assert confirm_env.config_service.set.await_args.kwargs["device_id"] == "plugin-import"
        # mcpServers contract is {mcpConfigs: [...]}; a bare list would be unreadable by the runtime config loader.
        assert set(set_args[1]) == {"mcpConfigs"}
        persisted = set_args[1]["mcpConfigs"]
        assert len(persisted) == 1
        assert persisted[0]["name"] == "pdf-server"
        assert persisted[0]["enabled"] is False
        assert persisted[0]["command"] == "./bin/pdf"
        confirm_env.invalidate_cache.assert_called_once()

        # Binding appends only what this import installed, keeping the expert's own entries.
        confirm_env.agent_service.update_agent.assert_awaited_once()
        update = confirm_env.agent_service.update_agent.await_args.args[1]
        assert update.mcp_ids == ["existing", "pdf-server"]
        assert update.skill_ids == ["existing-skill", compute_local_skill_id(skill_dir)]

    async def test_duplicate_server_name_not_counted_or_bound(self, confirm_env: SimpleNamespace) -> None:
        session = _parse_session()
        server_keys = list(session.servers_by_key)
        confirm_env.config_service.get.return_value = SimpleNamespace(
            value={"mcpConfigs": [{"name": "pdf-server", "enabled": True}]}
        )

        result = await confirm_plugin_import(
            session,
            skill_decisions=[],
            server_decisions=[_decision("mcp", server_keys[0], "pdf-server")],
            bind_agent_id="agent-1",
        )

        assert result == EMPTY_RESULT
        confirm_env.config_service.set.assert_not_awaited()
        confirm_env.invalidate_cache.assert_not_called()
        confirm_env.agent_service.update_agent.assert_not_awaited()

    async def test_skip_everything(self, confirm_env: SimpleNamespace) -> None:
        session = _parse_session()
        skill_key = next(iter(session.skills_by_key))
        server_key = next(iter(session.servers_by_key))

        result = await confirm_plugin_import(
            session,
            skill_decisions=[_decision("skill", skill_key, "summarize", "skip")],
            server_decisions=[_decision("mcp", server_key, "pdf-server", "skip")],
        )

        assert result == {**EMPTY_RESULT, "skipped_skills": 1, "skipped_servers": 1}
        assert list(confirm_env.skills_dir.iterdir()) == []
        confirm_env.mount.assert_not_awaited()
        confirm_env.config_service.set.assert_not_awaited()
        confirm_env.agent_service.update_agent.assert_not_awaited()

    async def test_merges_existing_mcp_configs(self, confirm_env: SimpleNamespace) -> None:
        session = _parse_session()
        server_keys = list(session.servers_by_key)
        confirm_env.config_service.get.return_value = SimpleNamespace(
            value={"mcpConfigs": [{"name": "pdf-server", "enabled": True, "command": "/old"}]}
        )

        await confirm_plugin_import(
            session,
            skill_decisions=[],
            server_decisions=[
                _decision("mcp", server_keys[0], "pdf-server"),
                _decision("mcp", server_keys[1], "remote"),
            ],
        )

        persisted_value = confirm_env.config_service.set.await_args.args[1]
        # Existing pdf-server kept as-is; remote appended (skipping the duplicate).
        assert [cfg["name"] for cfg in persisted_value["mcpConfigs"]] == ["pdf-server", "remote"]
        assert persisted_value["mcpConfigs"][1]["enabled"] is False
        assert persisted_value["mcpConfigs"][1]["type"] == "streamable_http"
        assert persisted_value["mcpConfigs"][1]["url"] == "https://api.example.com/mcp"
        confirm_env.invalidate_cache.assert_called_once()

    async def test_preserves_legacy_bare_list_mcp_configs(self, confirm_env: SimpleNamespace) -> None:
        """User-configured servers (incl. legacy bare-list payloads) survive import.

        The persisted shape is always ``{"mcpConfigs": [...]}`` and existing names
        are merged with imported ones, never dropped.
        """
        session = _parse_session()
        server_key = next(iter(session.servers_by_key))
        confirm_env.config_service.get.return_value = SimpleNamespace(
            value=[{"name": "user-mcp", "enabled": True, "command": "/keep-me"}]
        )

        await confirm_plugin_import(
            session,
            skill_decisions=[],
            server_decisions=[_decision("mcp", server_key, "pdf-server")],
        )

        persisted_value = confirm_env.config_service.set.await_args.args[1]
        assert [cfg["name"] for cfg in persisted_value["mcpConfigs"]] == ["user-mcp", "pdf-server"]
        assert persisted_value["mcpConfigs"][0]["command"] == "/keep-me"
        confirm_env.invalidate_cache.assert_called_once()

    async def test_skill_with_security_issues_is_reported_and_leaves_nothing_behind(self, confirm_env: SimpleNamespace) -> None:
        session = _parse_session()
        skill_key = next(iter(session.skills_by_key))

        with patch("app.services.plugins._gates.scan_skill_security", return_value=["Dangerous pattern detected"]):
            result = await confirm_plugin_import(
                session,
                skill_decisions=[_decision("skill", skill_key, "summarize")],
                server_decisions=[],
            )

        assert result == {
            **EMPTY_RESULT,
            "failures": [
                {
                    "component": "skill",
                    "name": "summarize",
                    "code": "security_issues",
                    "message": "Dangerous pattern detected",
                }
            ],
        }
        assert list(confirm_env.skills_dir.iterdir()) == []
        confirm_env.mount.assert_not_awaited()
        confirm_env.config_service.set.assert_not_awaited()

    async def test_oversized_skill_content_is_reported_with_its_own_code(self, confirm_env: SimpleNamespace) -> None:
        from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

        session = _parse_session()
        skill_key = next(iter(session.skills_by_key))
        session.skills_by_key[skill_key] = PluginSkill(
            name="huge",
            description="Too big",
            content="x" * (SkillStore.MAX_SKILL_CONTENT_CHARS + 1),
            files={"SKILL.md": b"---\nname: huge\ndescription: Too big\n---\nbody"},
        )

        result = await confirm_plugin_import(
            session,
            skill_decisions=[_decision("skill", skill_key, "huge")],
            server_decisions=[],
        )

        assert result["imported_skills"] == 0
        assert [(f["name"], f["code"]) for f in result["failures"]] == [("huge", "oversized_content")]
        assert list(confirm_env.skills_dir.iterdir()) == []

    async def test_skills_disabled_deployment_reports_instead_of_installing(
        self, confirm_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.plugins.import_service.load_preview_context",
            AsyncMock(return_value=PreviewContext(allows_local_skills=False)),
        )
        session = _parse_session()
        skill_key = next(iter(session.skills_by_key))

        result = await confirm_plugin_import(
            session,
            skill_decisions=[_decision("skill", skill_key, "summarize")],
            server_decisions=[],
        )

        assert [(f["component"], f["code"]) for f in result["failures"]] == [("skill", "skills_not_supported")]
        assert list(confirm_env.skills_dir.iterdir()) == []

    async def test_stdio_connector_is_reported_when_the_deployment_forbids_it(
        self, confirm_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.plugins.import_service.load_preview_context",
            AsyncMock(return_value=PreviewContext(allow_stdio=False)),
        )
        session = _parse_session()
        server_keys = list(session.servers_by_key)

        result = await confirm_plugin_import(
            session,
            skill_decisions=[],
            server_decisions=[
                _decision("mcp", server_keys[0], "pdf-server"),
                _decision("mcp", server_keys[1], "remote"),
            ],
        )

        assert [(f["name"], f["code"]) for f in result["failures"]] == [("pdf-server", "stdio_not_allowed")]
        assert result["imported_servers"] == 1  # the remote connector still lands
        persisted = confirm_env.config_service.set.await_args.args[1]["mcpConfigs"]
        assert [cfg["name"] for cfg in persisted] == ["remote"]

    async def test_reinstalling_a_skill_upgrades_it_in_place(self, confirm_env: SimpleNamespace) -> None:
        session = _parse_session()
        skill_key = next(iter(session.skills_by_key))
        decisions = [_decision("skill", skill_key, "summarize")]

        first = await confirm_plugin_import(session, skill_decisions=decisions, server_decisions=[])
        upgraded = PluginSkill(
            name="summarize",
            description="Do summaries",
            content="Better work.",
            files={"SKILL.md": b"---\nname: summarize\ndescription: Do summaries\n---\nBetter work."},
        )
        session.skills_by_key[skill_key] = upgraded
        second = await confirm_plugin_import(session, skill_decisions=decisions, server_decisions=[])

        assert first["imported_skills"] == 1 and second["imported_skills"] == 1
        assert second["failures"] == []
        assert sorted(p.name for p in confirm_env.skills_dir.iterdir()) == ["summarize"]
        assert b"Better work." in (confirm_env.skills_dir / "summarize" / "SKILL.md").read_bytes()

    async def test_persists_scoped_secrets_and_headers(self, confirm_env: SimpleNamespace) -> None:
        """Imported servers persist required_secrets and secret header refs.

        ``env_key_names`` become ``required_secrets`` for runtime Scoped Secret
        Injection, and header values that are already ``{{secret:KEY}}`` refs are
        preserved verbatim while plaintext values are rewritten to refs, so
        credentials never land in the store as plaintext.
        """
        session = _parse_session()
        server_key = next(iter(session.servers_by_key))
        session.servers_by_key[server_key] = PluginMcpServer(
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

        result = await confirm_plugin_import(
            session,
            skill_decisions=[],
            server_decisions=[_decision("mcp", server_key, "auth-server")],
        )

        assert result["imported_servers"] == 1
        # env_key_names + header refs (incl. rewritten plaintext refs), deduped.
        assert result["required_secret_keys"] == ["API_TOKEN", "REGION", "X-Client"]

        entry = confirm_env.config_service.set.await_args.args[1]["mcpConfigs"][0]
        assert entry["required_secrets"] == ["API_TOKEN", "REGION"]
        # Existing secret ref preserved verbatim; plaintext rewritten to a ref.
        assert entry["headers"]["Authorization"] == "Bearer {{secret:API_TOKEN}}"
        assert entry["headers"]["X-Client"] == "{{secret:X-Client}}"
        confirm_env.invalidate_cache.assert_called_once()


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
                "app.services.plugins._uninstall._plugin_dir_exists",
                side_effect=lambda name: name == "demo-plugin",
            ),
        ):
            items = await list_installed_plugins()

        assert items == [
            {
                "name": "demo-plugin",
                "servers": ["pdf-server", "remote"],
                "server_meta": [
                    {"name": "pdf-server", "enabled": False, "capabilities": []},
                    {"name": "remote", "enabled": True, "capabilities": []},
                ],
                "has_bundled_files": True,
                "capabilities": [],
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
            patch("app.services.plugins.import_service.load_preview_context", AsyncMock(return_value=PreviewContext())),
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

    @pytest.mark.asyncio
    async def test_confirm_skips_oversized_template_files(self) -> None:
        from myrm_agent_harness.agent.plugins.rules import MAX_TEMPLATE_FILE_BYTES

        zip_bytes = _plugin_zip_with_agents_bytes()
        result = parse_plugin_zip(zip_bytes)
        # Add an oversized file to workspace_files
        result.workspace_files["huge_data.bin"] = b"X" * (MAX_TEMPLATE_FILE_BYTES + 10)
        result.workspace_files["normal.txt"] = b"normal content"

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

        captured_engine_params: list[dict] = []

        async def capture_create_agent(dto):
            if dto.engine_params:
                captured_engine_params.append(dto.engine_params)
            return SimpleNamespace(id=f"id-{dto.name}", name=dto.name)

        with (
            patch("app.services.agent.agent_service.AgentService.create_agent", side_effect=capture_create_agent),
            patch("app.services.plugins.import_service.load_preview_context", AsyncMock(return_value=PreviewContext())),
        ):
            await confirm_plugin_import(
                session,
                skill_decisions=[],
                server_decisions=[],
                agent_decisions=agent_decisions,
            )

        assert len(captured_engine_params) > 0
        templates = captured_engine_params[0]["template_workspace_files"]
        # Normal files are included
        assert "template.xlsx" in templates or "normal.txt" in templates
        # Oversized file is safely skipped!
        assert "huge_data.bin" not in templates

    def test_preview_warns_oversized_template_files(self) -> None:
        from myrm_agent_harness.agent.plugins.rules import MAX_TEMPLATE_FILE_BYTES

        from app.services.plugins._preview import build_preview_result

        zip_bytes = _plugin_zip_with_agents_bytes()
        result = parse_plugin_zip(zip_bytes)
        result.workspace_files["oversized_data.bin"] = b"Y" * (MAX_TEMPLATE_FILE_BYTES + 50)

        preview = build_preview_result(result)
        codes = [d["code"] for d in preview["diagnostics"]]
        assert "OVERSIZED_TEMPLATE_FILE" in codes
        warning_msg = next(d["message"] for d in preview["diagnostics"] if d["code"] == "OVERSIZED_TEMPLATE_FILE")
        assert "oversized_data.bin" in warning_msg
        assert "exceeds 1MB limit" in warning_msg

    @pytest.mark.asyncio
    async def test_materialize_agent_template_files_security_and_writing(self, tmp_path: Path) -> None:
        """Verifies that _materialize_agent_template_files writes text/base64 files and blocks path traversal."""
        import base64

        from app.services.agent.params.workspace_resolve import _materialize_agent_template_files

        chat_id = "test-chat-materialize-1"
        target_workspace = tmp_path / "sandbox_ws"
        target_workspace.mkdir(parents=True, exist_ok=True)

        # Pre-existing file should not be overwritten
        (target_workspace / "existing.txt").write_text("initial content", encoding="utf-8")

        mock_chat = SimpleNamespace(agent_id="test-agent-with-templates")
        b64_data = base64.b64encode(b"binary asset data").decode("utf-8")
        mock_profile = SimpleNamespace(
            engine_params={
                "template_workspace_files": {
                    "templates/report.md": "# Research Report Template",
                    "assets/logo.png": f"base64:{b64_data}",
                    "existing.txt": "overwritten content should not happen",
                    "../escape.txt": "malicious content",
                }
            }
        )

        mock_resolver = SimpleNamespace(resolve=AsyncMock(return_value=mock_profile))

        with (
            patch("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=mock_chat)),
            patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
        ):
            await _materialize_agent_template_files(chat_id, str(target_workspace))

        # 1. Normal text file written
        report_file = target_workspace / "templates" / "report.md"
        assert report_file.exists()
        assert report_file.read_text(encoding="utf-8") == "# Research Report Template"

        # 2. Base64 decoded binary file written
        logo_file = target_workspace / "assets" / "logo.png"
        assert logo_file.exists()
        assert logo_file.read_bytes() == b"binary asset data"

        # 3. Existing file preserved
        existing_file = target_workspace / "existing.txt"
        assert existing_file.read_text(encoding="utf-8") == "initial content"

        # 4. Path traversal blocked
        escape_file = tmp_path / "escape.txt"
        assert not escape_file.exists()

    def test_preview_capabilities_and_risk_level(self) -> None:
        from app.services.plugins._preview import build_preview_result

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "plugin.json",
                json.dumps(
                    {
                        "$schema": PLUGIN_SCHEMA,
                        "name": "shell-plugin",
                        "version": "1.0.0",
                    }
                ),
            )
            zf.writestr(
                "mcp.json",
                json.dumps(
                    {
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                        "mcpServers": {
                            "runner": {
                                "type": "stdio",
                                "command": "./run.sh",
                            }
                        },
                    }
                ),
            )
            zf.writestr("run.sh", "#!/bin/sh\necho ok")
        result = parse_plugin_zip(buf.getvalue())
        preview = build_preview_result(result)

        plugin_meta = preview["plugin"]
        assert "shell_exec" in plugin_meta["capabilities"]
        assert plugin_meta["effective_tier"] == "shell_exec"
        assert plugin_meta["risk_level"] == "high"

    def test_preview_capability_diff_and_escalation(self) -> None:
        from app.services.plugins._preview import build_preview_result

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "plugin.json",
                json.dumps(
                    {
                        "$schema": PLUGIN_SCHEMA,
                        "name": "escalated-plugin",
                        "version": "2.0.0",
                    }
                ),
            )
            zf.writestr(
                "mcp.json",
                json.dumps(
                    {
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                        "mcpServers": {
                            "runner": {
                                "type": "stdio",
                                "command": "./run.sh",
                            }
                        },
                    }
                ),
            )
            zf.writestr("run.sh", "#!/bin/sh\necho ok")
        result = parse_plugin_zip(buf.getvalue())

        # Old version only had read_only
        installed_caps = {"read_only"}
        preview = build_preview_result(result, installed_capabilities=installed_caps)

        diff = preview["plugin"]["capability_diff"]
        assert diff is not None
        assert "shell_exec" in diff["added"]
        assert diff["has_escalation"] is True


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
