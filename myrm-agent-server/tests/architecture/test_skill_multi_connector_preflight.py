"""Architecture guard: Test skill multi-connector preflight gates.

[INPUT]
- app.core.skills.gates.oauth_availability::apply_integration_oauth_to_metadata
- myrm_agent_harness.backends.skills.types::SkillMetadata
- tests.support.skill_credential_store::credentials (the OAuth tokens stored for the issuers)

[OUTPUT]
- Tests verifying multi-connector required_oauth_issuers preflight and availability marking against stored tokens.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.skills.gates.oauth_availability import (
    apply_integration_oauth_to_metadata,
)
from tests.support.skill_credential_store import CredentialStore


@pytest.mark.asyncio
async def test_multi_connector_preflight_marks_unavailable_when_issuer_missing(credentials: CredentialStore) -> None:
    # Skill requiring two issuers: google_workspace and spotify
    meta = SkillMetadata(
        name="multi-meeting-sync",
        description="Multi meeting sync test skill",
        storage_path="/tmp/fake-skill",
        required_oauth_issuers=["google_workspace", "spotify"],
    )
    # google is connected, but spotify is not
    await credentials.store_oauth({"google_workspace": {"token": "google-token"}})

    async with credentials.sessions() as db:
        await apply_integration_oauth_to_metadata([meta], db)

    assert meta.available is False
    assert "spotify" in (meta.unavailable_reason or "")
    assert "Settings → Integrations → Credentials" in (meta.unavailable_reason or "")


@pytest.mark.asyncio
async def test_multi_connector_preflight_keeps_available_when_all_issuers_connected(credentials: CredentialStore) -> None:
    meta = SkillMetadata(
        name="multi-meeting-sync-full",
        description="Multi meeting sync full test skill",
        storage_path="/tmp/fake-skill",
        required_oauth_issuers=["google_workspace", "slack"],
    )
    await credentials.store_oauth({"google_workspace": {"token": "google-token"}, "slack": {"token": "slack-token"}})

    async with credentials.sessions() as db:
        await apply_integration_oauth_to_metadata([meta], db)

    assert meta.available is True
    assert meta.unavailable_reason is None
