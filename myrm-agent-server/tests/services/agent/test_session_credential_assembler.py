"""Tests for SessionCredentialAssembler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security import CredentialTrack, user_credentials_ctx

from app.services.agent.session_credential_assembler import (
    XAI_ISSUER,
    assemble_session_credentials,
    user_config_session_credentials_scope,
)


@pytest.mark.asyncio
async def test_assemble_oauth_and_xai_provider_credentials() -> None:
    oauth_dict = {
        "google_workspace": {
            "token": "oauth-token",
            "scope": "email",
            "user_id": "u1",
        }
    }
    providers_dict = {
        "providers": [
            {"id": "xai-main", "apiKeys": [{"key": "xai-key", "isActive": True}], "apiUrl": "https://api.x.ai/v1"},
        ]
    }

    with patch(
        "app.services.agent.oauth_refresher.refresh_oauth_token",
        new_callable=AsyncMock,
    ):
        credentials = await assemble_session_credentials(
            oauth_credentials_dict=oauth_dict,
            providers_dict=providers_dict,
        )

    issuers = {cred.issuer for cred in credentials}
    assert "google_workspace" in issuers
    assert XAI_ISSUER in issuers

    xai_cred = next(c for c in credentials if c.issuer == XAI_ISSUER)
    assert xai_cred.token == "xai-key"
    assert xai_cred.scope == "https://api.x.ai/v1"


@pytest.mark.asyncio
async def test_assemble_merges_channel_token_with_oauth() -> None:
    oauth_dict = {"google_workspace": {"token": "oauth-token"}}

    mock_store = MagicMock()
    mock_store.get = AsyncMock(
        return_value={"user_access_token": "channel-token", "user_id": "peer-1"},
    )

    with (
        patch(
            "app.services.agent.oauth_refresher.refresh_oauth_token",
            new_callable=AsyncMock,
        ),
        patch("app.channels.storage.CredentialsStore", return_value=mock_store),
    ):
        credentials = await assemble_session_credentials(
            oauth_credentials_dict=oauth_dict,
            channel="feishu",
        )

    issuers = {cred.issuer for cred in credentials}
    assert "google_workspace" in issuers
    assert "feishu" in issuers


@pytest.mark.asyncio
async def test_assemble_returns_empty_on_total_failure() -> None:
    with patch(
        "app.services.agent.session_credential_assembler._oauth_credentials_from_dict",
        side_effect=RuntimeError("boom"),
    ):
        credentials = await assemble_session_credentials(oauth_credentials_dict={"x": {"token": "t"}})

    assert credentials == ()


def test_xai_issuer_constant() -> None:
    assert XAI_ISSUER == "xai"


def _channel_store(*stored: dict[str, object] | None) -> MagicMock:
    """A channel credentials store that answers each ``get`` with the next stored entry, the last one repeating."""
    store = MagicMock()
    store.get = AsyncMock(side_effect=[*stored, *([stored[-1]] * 4)])
    return store


@pytest.mark.asyncio
async def test_a_stored_entry_that_is_not_a_mapping_or_holds_no_token_is_skipped() -> None:
    credentials = await assemble_session_credentials(
        oauth_credentials_dict={
            "legacy": "plain-string",
            "no_token": {"scope": "email"},
            "google_workspace": {"token": "oauth-token"},
        },
    )

    assert [credential.issuer for credential in credentials] == ["google_workspace"]


@pytest.mark.asyncio
async def test_a_shared_turn_is_still_handed_the_channel_token_and_nothing_personal() -> None:
    store = _channel_store({"user_access_token": "channel-token", "user_id": "peer-1"})

    with patch("app.channels.storage.CredentialsStore", return_value=store):
        credentials = await assemble_session_credentials(
            oauth_credentials_dict={"google_workspace": {"token": "owner-token"}},
            providers_dict={"providers": [{"id": "xai", "apiKeys": [{"key": "owner-key", "isActive": True}]}]},
            channel="feishu",
            credential_track=CredentialTrack.SHARED,
        )

    assert [(credential.issuer, credential.token, credential.user_id) for credential in credentials] == [
        ("feishu", "channel-token", "peer-1"),
    ]


@pytest.mark.parametrize(
    ("stored", "token"),
    [
        ({"user_access_token": "user-token", "access_token": "bot-token"}, "user-token"),
        ({"access_token": "bot-token"}, "bot-token"),
    ],
    ids=["user-token-wins", "bot-token-fallback"],
)
@pytest.mark.asyncio
async def test_the_channel_token_is_the_user_token_before_the_bot_token(stored: dict[str, object], token: str) -> None:
    with patch("app.channels.storage.CredentialsStore", return_value=_channel_store(stored)):
        credentials = await assemble_session_credentials(channel="feishu")

    assert [credential.token for credential in credentials] == [token]


@pytest.mark.parametrize("stored", [None, {}, {"user_id": "peer-1"}], ids=["nothing-stored", "empty", "no-token"])
@pytest.mark.asyncio
async def test_a_channel_without_a_stored_token_adds_no_credential(stored: dict[str, object] | None) -> None:
    with patch("app.channels.storage.CredentialsStore", return_value=_channel_store(stored)):
        credentials = await assemble_session_credentials(channel="feishu")

    assert credentials == ()


@pytest.mark.asyncio
async def test_the_channel_token_refresher_reads_the_store_again() -> None:
    store = _channel_store({"user_access_token": "old-token"}, {"user_access_token": "new-token", "user_id": "peer-2"})

    with patch("app.channels.storage.CredentialsStore", return_value=store):
        [credential] = await assemble_session_credentials(channel="feishu")

    assert credential.refresh_callback is not None
    refreshed = await credential.refresh_callback()

    assert refreshed is not None
    assert (refreshed.issuer, refreshed.token, refreshed.user_id) == ("feishu", "new-token", "peer-2")
    assert refreshed.refresh_callback is not None


@pytest.mark.parametrize("after", [None, {}, {"user_id": "peer-1"}], ids=["entry-removed", "entry-empty", "token-removed"])
@pytest.mark.asyncio
async def test_the_channel_token_refresher_gives_nothing_once_the_token_is_gone(after: dict[str, object] | None) -> None:
    store = _channel_store({"user_access_token": "old-token"}, after)

    with patch("app.channels.storage.CredentialsStore", return_value=store):
        [credential] = await assemble_session_credentials(channel="feishu")

    assert credential.refresh_callback is not None
    assert await credential.refresh_callback() is None


@pytest.mark.asyncio
async def test_the_user_config_scope_hands_the_turn_the_credentials_of_the_loaded_config() -> None:
    configs = SimpleNamespace(oauth_credentials_dict={"google_workspace": {"token": "oauth-token"}}, providers_dict=None)

    with patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=configs)):
        async with user_config_session_credentials_scope():
            issuers = [credential.issuer for credential in user_credentials_ctx.get()]

    assert issuers == ["google_workspace"]
    assert user_credentials_ctx.get() == ()


@pytest.mark.asyncio
async def test_the_user_config_scope_hands_nothing_when_no_config_can_be_loaded() -> None:
    with patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=None)):
        async with user_config_session_credentials_scope():
            assert user_credentials_ctx.get() == ()
