"""What a plugin import and uninstall do to the stored ``mcpServers`` row.

Every test runs the real config service over a real in-memory database, so a row sealed under a key that is gone, a read
that fails and the keys of the stored value besides ``mcpConfigs`` behave here the way they do for a user.
"""

from __future__ import annotations

import copy
import io
import json
import logging
import os
import zipfile
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core.channel_bridge.config_loader import load_user_configs
from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import service
from app.services.config.encryption import ConfigEncryptionService
from app.services.config.service import config_service
from app.services.plugins._mcp_persist import _remove_plugin_mcp_servers
from app.services.plugins._preview_context import PreviewContext
from app.services.plugins.import_service import (
    PluginConfirmItem,
    PluginImportSession,
    confirm_plugin_import,
    list_installed_plugins,
    parse_plugin_zip,
)
from tests.support.skill_credential_store import CredentialStore

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
IMPORTER = "plugin-import"
UNINSTALLER = "plugin-uninstall"
PERSIST_LOGGER = "app.services.plugins._mcp_persist"

OPENAI_ROW = {"id": "openai", "name": "openai", "isEnabled": True, "apiKeys": [{"id": "k1", "key": "sk-test", "isActive": True}]}
FS_SERVER = {"name": "fs", "type": "stdio", "command": "fs-server", "enabled": True}
DEMO_ENTRY = {
    "name": "docs",
    "type": "streamable_http",
    "url": "https://docs.example.com/mcp",
    "extra_params": {"plugin_name": "demo-plugin"},
}
OTHER_ENTRY = {
    "name": "wiki",
    "type": "streamable_http",
    "url": "https://wiki.example.com/mcp",
    "extra_params": {"plugin_name": "other"},
}


@pytest.fixture(autouse=True)
def _confirm_without_the_installation_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirm re-reads the installed skills and experts first; this suite is about the ``mcpServers`` row only."""
    monkeypatch.setattr("app.services.plugins.import_service.load_preview_context", AsyncMock(return_value=PreviewContext()))


def _session() -> tuple[PluginImportSession, list[PluginConfirmItem]]:
    """A package of two remote connectors (no bundled files) and the decision that installs both."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "demo/plugin.json",
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
        bundle.writestr(
            "demo/mcp.json",
            json.dumps(
                {
                    "$schema": MCP_SCHEMA,
                    "mcpServers": {
                        "docs": {"type": "streamable-http", "url": "https://docs.example.com/mcp"},
                        "search": {"type": "streamable-http", "url": "https://search.example.com/mcp"},
                    },
                }
            ),
        )
    result = parse_plugin_zip(archive.getvalue())
    servers = {f"mcp:{index}": server for index, server in enumerate(result.servers)}
    decisions = [PluginConfirmItem("mcp", key, "install", server.name) for key, server in servers.items()]
    return PluginImportSession(plugin_result=result, servers_by_key=servers), decisions


async def _import_servers() -> dict[str, object]:
    session, decisions = _session()
    return await confirm_plugin_import(session, skill_decisions=[], server_decisions=decisions)


def _entries(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]


async def _stored(key: str) -> dict[str, object]:
    record = await config_service.get(key)
    assert record is not None
    return record.value


async def _loaded_names() -> list[object]:
    """The server names the runtime reads from the stored list (every entry, enabled or not)."""
    mcp_dict = (await load_user_configs()).mcp_dict
    assert mcp_dict is not None
    return [cfg["name"] for cfg in _entries(mcp_dict["mcpConfigs"])]


async def _row(store: CredentialStore, key: str) -> tuple[dict[str, object], str]:
    """The row as the database holds it (sealed values stay sealed) with its version."""
    async with store.sessions() as db:
        row = (await db.execute(select(UserConfig).where(UserConfig.config_key == key))).scalar_one()
        return copy.deepcopy(row.config_value), row.version


async def _writers(store: CredentialStore, key: str) -> set[str]:
    async with store.sessions() as db:
        rows = (await db.execute(select(ConfigAuditLog).where(ConfigAuditLog.config_key == key))).scalars().all()
        return {row.device_id for row in rows}


def _lose_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seal-key loss: rows written so far can no longer be opened."""
    other = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr(service, "get_encryption_service", lambda: other)


# --- import ------------------------------------------------------------------------------------------------------


async def test_imported_servers_join_the_stored_list_disabled_and_the_next_load_sees_them(credentials: CredentialStore) -> None:
    await credentials.store_providers([OPENAI_ROW])
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(FS_SERVER)], "layout": "grid"}, device_id="web")
    # A turn before the import loaded the list, and the loader keeps what it loaded for a while.
    assert await _loaded_names() == ["fs"]

    result = await _import_servers()

    assert result["imported_servers"] == 2
    assert result["failures"] == []
    stored = await _stored("mcpServers")
    assert [(cfg["name"], cfg["enabled"]) for cfg in _entries(stored["mcpConfigs"])] == [
        ("fs", True),
        ("docs", False),
        ("search", False),
    ]
    assert stored["layout"] == "grid"
    assert await _writers(credentials, "mcpServers") == {"web", IMPORTER}
    assert await _loaded_names() == ["fs", "docs", "search"]


async def test_the_first_import_creates_the_row(credentials: CredentialStore) -> None:
    assert await config_service.get("mcpServers") is None

    result = await _import_servers()

    assert result["imported_servers"] == 2
    assert result["failures"] == []
    assert [cfg["name"] for cfg in _entries((await _stored("mcpServers"))["mcpConfigs"])] == ["docs", "search"]


async def test_a_row_sealed_under_a_lost_key_is_not_overwritten_by_an_import(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(FS_SERVER)]}, device_id="web")
    before = await _row(credentials, "mcpServers")
    _lose_the_key(monkeypatch)

    with caplog.at_level(logging.WARNING, logger=PERSIST_LOGGER):
        result = await _import_servers()

    assert result["imported_servers"] == 0
    assert [(f["component"], f["name"], f["code"]) for f in _entries(result["failures"])] == [
        ("mcp", "docs", "mcp_config_unreadable"),
        ("mcp", "search", "mcp_config_unreadable"),
    ]
    assert await _row(credentials, "mcpServers") == before
    assert IMPORTER not in await _writers(credentials, "mcpServers")
    assert "stored mcpServers cannot be read back" in caplog.text


async def test_a_failed_read_does_not_become_an_empty_list_that_replaces_the_stored_one(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(FS_SERVER)]}, device_id="web")
    before = await _row(credentials, "mcpServers")
    monkeypatch.setattr(config_service, "get", AsyncMock(side_effect=RuntimeError("database is locked")))

    result = await _import_servers()

    assert result["imported_servers"] == 0
    assert [f["code"] for f in _entries(result["failures"])] == ["mcp_config_unreadable", "mcp_config_unreadable"]
    assert await _row(credentials, "mcpServers") == before
    assert IMPORTER not in await _writers(credentials, "mcpServers")


# --- uninstall ---------------------------------------------------------------------------------------------------


async def test_uninstall_drops_only_the_plugin_entries_and_keeps_the_rest_of_the_row(credentials: CredentialStore) -> None:
    stored = {"mcpConfigs": [copy.deepcopy(DEMO_ENTRY), copy.deepcopy(FS_SERVER), copy.deepcopy(OTHER_ENTRY)], "layout": "grid"}
    await config_service.set("mcpServers", stored, device_id="web")

    assert await _remove_plugin_mcp_servers("demo-plugin") == 1

    assert await _stored("mcpServers") == {"mcpConfigs": [FS_SERVER, OTHER_ENTRY], "layout": "grid"}
    assert UNINSTALLER in await _writers(credentials, "mcpServers")


async def test_uninstall_leaves_a_row_sealed_under_a_lost_key_alone(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(DEMO_ENTRY)]}, device_id="web")
    before = await _row(credentials, "mcpServers")
    _lose_the_key(monkeypatch)

    with caplog.at_level(logging.WARNING, logger=PERSIST_LOGGER):
        assert await _remove_plugin_mcp_servers("demo-plugin") == 0

    assert await _row(credentials, "mcpServers") == before
    assert UNINSTALLER not in await _writers(credentials, "mcpServers")
    assert "stored mcpServers cannot be read back" in caplog.text


async def test_the_installed_plugin_list_shows_nothing_for_a_row_sealed_under_a_lost_key(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(DEMO_ENTRY)]}, device_id="web")
    assert [plugin["name"] for plugin in await list_installed_plugins()] == ["demo-plugin"]
    _lose_the_key(monkeypatch)

    assert await list_installed_plugins() == []
