"""Credential dual-track: shared turns never touch personal OAuth tokens.

Real assembler, realistically-shaped inputs, no mocks, no LLM.
"""

from __future__ import annotations

import pytest

from app.services.agent.session_credential_assembler import assemble_session_credentials

_OAUTH_DICT: dict[str, object] = {
    "google": {"token": "owner-google-token", "scope": "drive.readonly", "user_id": "owner-1"},
    "xai": {"token": "owner-xai-token", "base_url": "https://api.x.ai/v1", "user_id": "owner-1"},
}


@pytest.mark.asyncio
async def test_shared_track_excludes_personal_oauth() -> None:
    creds = await assemble_session_credentials(
        oauth_credentials_dict=_OAUTH_DICT,
        providers_dict=None,
        channel="feishu",
        credential_track="shared",
    )
    issuers = {c.issuer for c in creds}
    assert "google" not in issuers
    assert "xai" not in issuers
    for cred in creds:
        assert "owner-google-token" not in cred.token
        assert "owner-xai-token" not in cred.token


@pytest.mark.asyncio
async def test_personal_track_keeps_owner_oauth() -> None:
    creds = await assemble_session_credentials(
        oauth_credentials_dict=_OAUTH_DICT,
        providers_dict=None,
        channel="feishu",
    )
    issuers = {c.issuer for c in creds}
    assert "google" in issuers
    assert "xai" in issuers
