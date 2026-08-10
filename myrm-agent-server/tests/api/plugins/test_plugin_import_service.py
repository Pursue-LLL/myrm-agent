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
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.plugins.models import PluginSkill
from myrm_agent_harness.agent.plugins.parser import AgentPluginParser

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
            zf.writestr(
                "p/plugin.json", json.dumps({"$schema": PLUGIN_SCHEMA, "name": "big"})
            )
            for i in range(4200):
                zf.writestr(f"p/skills/s{i:04d}/SKILL.md", "x")
        with pytest.raises(ValueError) as excinfo:
            parse_plugin_zip(buf.getvalue())
        assert not isinstance(excinfo.value, ArchiveSecurityError)


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
        )
        config_service = SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
        )
        agent_service = SimpleNamespace(
            get_agent_by_id=AsyncMock(
                return_value=SimpleNamespace(metadata={"mcp_ids": ["existing"]})
            ),
            update_agent=AsyncMock(),
        )

        with (
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
        assert set_args[0] == "mcpServers"
        persisted = set_args[1]
        assert len(persisted) == 1
        assert persisted[0]["name"] == "pdf-server"
        assert persisted[0]["enabled"] is False
        assert persisted[0]["command"] == "./bin/pdf"

        # Agent binding appends only installed server names.
        agent_service.update_agent.assert_awaited_once()
        update = agent_service.update_agent.await_args.args[1]
        assert update.mcp_ids == ["existing", "pdf-server"]

    async def test_confirm_duplicate_server_name_not_counted_or_bound(
        self, tmp_path: Path
    ) -> None:
        session = self._make_session()
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(db_path=tmp_path, save_skills_batch=AsyncMock())
        config_service = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    value=[{"name": "pdf-server", "enabled": True}]
                )
            ),
            set=AsyncMock(),
        )
        agent_service = SimpleNamespace(
            get_agent_by_id=AsyncMock(
                return_value=SimpleNamespace(metadata={"mcp_ids": ["existing"]})
            ),
            update_agent=AsyncMock(),
        )

        with (
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
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
        }
        config_service.set.assert_not_awaited()
        agent_service.update_agent.assert_not_awaited()

    async def test_confirm_skip_everything(self, tmp_path: Path) -> None:
        session = self._make_session()
        skill_keys = list(session.skills_by_key.keys())
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(db_path=tmp_path, save_skills_batch=AsyncMock())
        config_service = SimpleNamespace(
            get=AsyncMock(return_value=None), set=AsyncMock()
        )
        agent_service = SimpleNamespace(
            get_agent_by_id=AsyncMock(), update_agent=AsyncMock()
        )

        with (
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
        }
        fake_store.save_skills_batch.assert_not_awaited()
        config_service.set.assert_not_awaited()
        agent_service.update_agent.assert_not_awaited()

    async def test_confirm_merges_existing_mcp_configs(self, tmp_path: Path) -> None:
        session = self._make_session()
        server_keys = list(session.servers_by_key.keys())

        fake_store = SimpleNamespace(db_path=tmp_path, save_skills_batch=AsyncMock())
        config_service = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    value=[{"name": "pdf-server", "enabled": True, "command": "/old"}]
                )
            ),
            set=AsyncMock(),
        )
        agent_service = SimpleNamespace(
            get_agent_by_id=AsyncMock(), update_agent=AsyncMock()
        )

        with (
            patch(
                "app.core.skills.store.evolution_store.get_evolution_skill_store",
                return_value=fake_store,
            ),
            patch("app.services.config.service.config_service", config_service),
            patch("app.services.agent.agent_service.AgentService", agent_service),
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
        persisted = set_args[1]
        # Existing pdf-server kept as-is; remote appended (skipping the duplicate).
        names = [cfg["name"] for cfg in persisted]
        assert names == ["pdf-server", "remote"]
        assert persisted[1]["enabled"] is False
        assert persisted[1]["type"] == "streamable_http"
        assert persisted[1]["url"] == "https://api.example.com/mcp"

    async def test_confirm_skips_skill_with_security_issues(
        self, tmp_path: Path
    ) -> None:
        session = _parse_session()
        skill_keys = list(session.skills_by_key.keys())

        fake_store = SimpleNamespace(db_path=tmp_path, save_skills_batch=AsyncMock())
        config_service = SimpleNamespace(
            get=AsyncMock(return_value=None), set=AsyncMock()
        )
        agent_service = SimpleNamespace(
            get_agent_by_id=AsyncMock(), update_agent=AsyncMock()
        )

        with (
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
        }
        fake_store.save_skills_batch.assert_not_awaited()
        config_service.set.assert_not_awaited()


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
