"""Integration: plugin MCP servers flow through the real config pipeline.

Full-chain verification of the plugin import ``enabled`` lifecycle WITHOUT
mocking the critical path (real ConfigService + real UserConfig table):

1. ``config_service.set("mcpServers", {mcpConfigs: [...]})`` persists both an
   enabled and a disabled server entry (the same shape ``_write_mcp_servers``
   writes on import — ``enabled=False`` default, ``extra_params.plugin_name``
   provenance marker).
2. ``list_installed_plugins`` reads the persisted entries back through the real
   encrypted-at-rest loader and reports each server's real ``enabled`` state.
3. ``extract_mcp_configs`` (the only runtime filter) drops the disabled entry,
   so the harness tool-discovery stage never receives it.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import delete, select

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.database.connection import get_session_factory
from app.database.models import UserConfig
from app.services.config.service import config_service
from app.services.plugins.import_service import list_installed_plugins


@pytest.fixture(autouse=True)
def _cleanup_mcp_servers_config() -> None:
    """Remove the mcpServers row before and after the test."""

    async def _remove() -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            row = (await session.execute(select(UserConfig).where(UserConfig.config_key == "mcpServers"))).scalar_one_or_none()
            if row is not None:
                await session.execute(delete(UserConfig).where(UserConfig.config_key == "mcpServers"))
                await session.commit()
        invalidate_user_configs_cache()

    asyncio.run(_remove())
    yield
    asyncio.run(_remove())


@pytest.mark.asyncio
async def test_plugin_mcp_enabled_chain_runs_through_real_config() -> None:
    """Persist → list (enabled read-back) → extract (runtime filter) → route."""
    await config_service.set(
        "mcpServers",
        {
            "mcpConfigs": [
                {
                    "name": "pdf-server",
                    "type": "stdio",
                    "command": "pdf-server-binary-does-not-exist",
                    "description": "Imported via Agent Plugin",
                    "enabled": False,
                    "extra_params": {"plugin_name": "demo-plugin"},
                },
                {
                    "name": "db-server",
                    "type": "stdio",
                    "command": "db-server-binary-does-not-exist",
                    "description": "Imported via Agent Plugin",
                    "enabled": True,
                    "extra_params": {"plugin_name": "demo-plugin"},
                },
            ]
        },
        device_id="plugin-import",
    )
    invalidate_user_configs_cache()

    # 2) The installed-plugin listing reads real persisted state back through
    #    the encrypted loader — enabled must round-trip truthfully.
    installed = await list_installed_plugins()
    assert len(installed) == 1
    plugin = installed[0]
    assert plugin["name"] == "demo-plugin"
    assert plugin["servers"] == ["db-server", "pdf-server"]
    assert plugin["server_meta"] == [
        {"name": "db-server", "enabled": True},
        {"name": "pdf-server", "enabled": False},
    ]

    # 3) The runtime filter keeps only the enabled server.
    from app.core.channel_bridge.config_parsers import extract_mcp_configs

    record = await config_service.get("mcpServers")
    assert record is not None
    loaded = record.value
    assert isinstance(loaded, dict)
    configs = extract_mcp_configs(loaded)
    assert [cfg.name for cfg in configs] == ["db-server"]

    # 4) The original persisted raw entries preserve the disabled marker — the
    #    disabled server is dropped at the only runtime filter, never reaching
    #    the harness routing/tool-discovery stage.
    raw_entries: list[dict[str, object]] = loaded["mcpConfigs"]
    disabled = next(c for c in raw_entries if c["name"] == "pdf-server")
    assert disabled["enabled"] is False
    assert disabled["extra_params"]["plugin_name"] == "demo-plugin"
