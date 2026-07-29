"""Tests for artifact_publish agent tool factory."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.hosting.agent_publish_tool import create_artifact_publish_tool
from app.services.hosting.types import HostingTarget, PublicationResult


@pytest.mark.asyncio
async def test_artifact_publish_returns_error_without_hosting_target() -> None:
    tool = create_artifact_publish_tool()

    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_session", return_value=mock_ctx),
        patch(
            "app.services.hosting.targets.get_default_hosting_target",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await tool.ainvoke({"artifact_id": "art-123"})

    assert result["metadata"]["error"] is True
    assert "No hosting target configured" in result["content"]


@pytest.mark.asyncio
async def test_artifact_publish_succeeds_with_default_target() -> None:
    tool = create_artifact_publish_tool()
    default_target = HostingTarget(
        id="tgt-001",
        name="My Vercel",
        provider_type="vercel",
        is_default=True,
    )
    pub_result = PublicationResult(
        success=True,
        url="https://my-app.vercel.app",
        publication_id="pub-001",
        project_ref="proj-001",
        status="DEPLOYED",
    )

    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_session", return_value=mock_ctx),
        patch(
            "app.services.hosting.targets.get_default_hosting_target",
            new_callable=AsyncMock,
            return_value=default_target,
        ),
        patch(
            "app.services.hosting.orchestrator.publish_artifact_to_target",
            new_callable=AsyncMock,
            return_value=pub_result,
        ),
        patch(
            "app.platform_utils.workspace_root.get_workspace_root",
            return_value="/test/workspace",
        ),
    ):
        result = await tool.ainvoke({"artifact_id": "art-456"})

    assert result["metadata"].get("error") is not True
    assert "https://my-app.vercel.app" in result["content"]
    assert result["metadata"]["hosting_target_id"] == "tgt-001"
