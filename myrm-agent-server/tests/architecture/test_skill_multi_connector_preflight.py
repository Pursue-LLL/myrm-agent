"""Architecture guard: Test skill multi-connector preflight gates.

[INPUT]
- app.core.skills.gates.oauth_availability::apply_integration_oauth_to_metadata
- myrm_agent_harness.backends.skills.types::SkillMetadata

[OUTPUT]
- Unit tests verifying multi-connector required_oauth_issuers preflight and availability marking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.skills.gates.oauth_availability import (
    apply_integration_oauth_to_metadata,
)


@pytest.mark.asyncio
async def test_multi_connector_preflight_marks_unavailable_when_issuer_missing() -> None:
    mock_db = AsyncMock()

    # Skill requiring two issuers: google_workspace and spotify
    meta = SkillMetadata(
        name="multi-meeting-sync",
        storage_path="/tmp/fake-skill",
        required_oauth_issuers=["google_workspace", "spotify"],
    )

    with patch(
        "app.core.skills.gates.oauth_availability.is_oauth_issuer_connected",
        new_callable=AsyncMock,
    ) as mock_conn:
        # google is connected, but spotify is not
        mock_conn.side_effect = lambda db, issuer: issuer == "google_workspace"

        await apply_integration_oauth_to_metadata([meta], mock_db)

        assert meta.available is False
        assert "spotify" in (meta.unavailable_reason or "")
        assert "Settings → Integrations → Credentials" in (meta.unavailable_reason or "")


@pytest.mark.asyncio
async def test_multi_connector_preflight_keeps_available_when_all_issuers_connected() -> None:
    mock_db = AsyncMock()

    meta = SkillMetadata(
        name="multi-meeting-sync-full",
        storage_path="/tmp/fake-skill",
        required_oauth_issuers=["google_workspace", "slack"],
    )

    with patch(
        "app.core.skills.gates.oauth_availability.is_oauth_issuer_connected",
        new_callable=AsyncMock,
    ) as mock_conn:
        mock_conn.return_value = True

        await apply_integration_oauth_to_metadata([meta], mock_db)

        assert meta.available is True
        assert meta.unavailable_reason is None
