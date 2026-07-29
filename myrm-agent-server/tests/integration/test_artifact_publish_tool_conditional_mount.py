"""Integration: artifact_publish tool conditional mount via _setup_artifact_publish_tool.

Verifies the tool registration gate: only mounted when has_any_hosting_credentials()
returns True, zero-overhead when unconfigured.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_artifact_publish_tool_mounts_when_credentials_present() -> None:
    """artifact_publish tool must appear in Turn1 tools when hosting is configured."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    tools: list[object] = []

    with patch(
        "app.services.hosting.credentials.has_any_hosting_credentials",
        new_callable=AsyncMock,
        return_value=True,
    ):
        await mixin._setup_artifact_publish_tool(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "artifact_publish"


@pytest.mark.asyncio
async def test_artifact_publish_tool_skipped_without_credentials() -> None:
    """Without hosting credentials, artifact_publish must not register at all."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    tools: list[object] = []

    with patch(
        "app.services.hosting.credentials.has_any_hosting_credentials",
        new_callable=AsyncMock,
        return_value=False,
    ):
        await mixin._setup_artifact_publish_tool(tools)

    assert len(tools) == 0


@pytest.mark.asyncio
async def test_artifact_publish_tool_graceful_on_import_error() -> None:
    """If hosting module fails to import, tool setup should not crash."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    tools: list[object] = []

    with patch(
        "app.services.hosting.credentials.has_any_hosting_credentials",
        side_effect=ImportError("hosting module unavailable"),
    ):
        await mixin._setup_artifact_publish_tool(tools)

    assert len(tools) == 0
